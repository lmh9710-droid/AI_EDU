"""
pt2onnx_cls.py : PyTorch 없이 Ultralytics 분류 모델(.pt) → ONNX 변환

  지원 블록 : Conv, C2f, C3k2, C3k, Bottleneck, C2PSA(PSABlock, Attention), Classify
              → YOLOv8-cls, YOLO11-cls 계열
  변환 방식 : 공식 export 와 동일하게 BatchNorm 을 Conv 가중치에 합치고(fuse) FP32 로 계산
  출력      : images[1,3,224,224] → output0[1,1000] (softmax 확률)

  사용법 : python pt2onnx_cls.py yolo11n-cls.pt [--labels labels.json] [-o out.onnx]
"""
import argparse
import json
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

from safe_pt import children, load_pt, tensors


class GraphBuilder:
    def __init__(self):
        self.nodes, self.inits, self.n = [], [], 0

    def uid(self, p):
        self.n += 1
        return f"{p}_{self.n}"

    def const(self, arr, p="c"):
        name = self.uid(p)
        self.inits.append(numpy_helper.from_array(np.asarray(arr), name))
        return name

    def op(self, op_type, inputs, p=None, **attrs):
        out = self.uid(p or op_type)
        self.nodes.append(helper.make_node(op_type, inputs, [out], **attrs))
        return out

    def split(self, x, sizes, axis=1):
        outs = [self.uid("split") for _ in sizes]
        self.nodes.append(helper.make_node("Split", [x, self.const(np.array(sizes, np.int64))],
                                           outs, axis=axis))
        return outs


def kind(m):
    return m._type.split(".")[-1]


class Converter:
    def __init__(self):
        self.g = GraphBuilder()

    # ---- Conv = SiLU(BN(Conv2d(x))) ; BN 은 가중치에 합침 -----------------------
    def conv(self, m, x, shape):
        c = children(m)
        cv, bn, act = c["conv"], c["bn"], c["act"]
        w = tensors(cv)["weight"].astype(np.float32)
        b = tensors(cv).get("bias")
        b = np.zeros(w.shape[0], np.float32) if b is None else b.astype(np.float32)
        t = tensors(bn)
        gamma, beta = t["weight"].astype(np.float32), t["bias"].astype(np.float32)
        mean, var = t["running_mean"].astype(np.float32), t["running_var"].astype(np.float32)
        s = gamma / np.sqrt(var + bn.eps)
        w = w * s[:, None, None, None]
        b = (b - mean) * s + beta

        k, st, pd, dl = cv.kernel_size, cv.stride, cv.padding, cv.dilation
        y = self.g.op("Conv", [x, self.g.const(w, "W"), self.g.const(b, "B")], "conv",
                      kernel_shape=list(k), strides=list(st), pads=[pd[0], pd[1], pd[0], pd[1]],
                      dilations=list(dl), group=cv.groups)
        C, H, W = shape
        H = (H + 2 * pd[0] - dl[0] * (k[0] - 1) - 1) // st[0] + 1
        W = (W + 2 * pd[1] - dl[1] * (k[1] - 1) - 1) // st[1] + 1
        if kind(act) == "SiLU":                       # SiLU(x) = x * sigmoid(x)
            y = self.g.op("Mul", [y, self.g.op("Sigmoid", [y])], "silu")
        elif kind(act) != "Identity":
            raise NotImplementedError(f"활성화 함수 {kind(act)}")
        return y, (w.shape[0], H, W)

    # ---- Bottleneck : x + cv2(cv1(x)) -------------------------------------------
    def bottleneck(self, m, x, shape):
        c = children(m)
        y, s = self.conv(c["cv1"], x, shape)
        y, s = self.conv(c["cv2"], y, s)
        if m.add:
            y = self.g.op("Add", [x, y])
        return y, s

    def seq(self, mods, x, shape):
        for sub in mods:
            x, shape = self.module(sub, x, shape)
        return x, shape

    # ---- C2f / C3k2 : cv1 → 반으로 나눔 → 블록을 이어 붙이며 모두 concat → cv2 ---
    def c2f(self, m, x, shape):
        c = children(m)
        y, s = self.conv(c["cv1"], x, shape)
        ys = self.g.split(y, [m.c, m.c])
        cur_s = (m.c, s[1], s[2])
        for sub in children(c["m"]).values():
            out, cur_s = self.module(sub, ys[-1], cur_s)
            ys.append(out)
        cat = self.g.op("Concat", ys, axis=1)
        return self.conv(c["cv2"], cat, (sum([m.c * 2] + [cur_s[0]] * (len(ys) - 2)), s[1], s[2]))

    # ---- C3k : cv3( concat( m(cv1(x)), cv2(x) ) ) -------------------------------
    def c3(self, m, x, shape):
        c = children(m)
        a, sa = self.conv(c["cv1"], x, shape)
        a, sa = self.seq(children(c["m"]).values(), a, sa)
        b, sb = self.conv(c["cv2"], x, shape)
        cat = self.g.op("Concat", [a, b], axis=1)
        return self.conv(c["cv3"], cat, (sa[0] + sb[0], sa[1], sa[2]))

    # ---- Attention (YOLO11 PSA) --------------------------------------------------
    def attention(self, m, x, shape):
        c = children(m)
        C, H, W = shape
        N, nh, kd, hd = H * W, m.num_heads, m.key_dim, m.head_dim
        qkv, _ = self.conv(c["qkv"], x, shape)
        qkv = self.g.op("Reshape", [qkv, self.g.const(np.array([1, nh, 2 * kd + hd, N], np.int64))])
        q, k, v = self.g.split(qkv, [kd, kd, hd], axis=2)
        qT = self.g.op("Transpose", [q], perm=[0, 1, 3, 2])
        attn = self.g.op("MatMul", [qT, k])
        attn = self.g.op("Mul", [attn, self.g.const(np.array(m.scale, np.float32))])
        attn = self.g.op("Softmax", [attn], axis=-1)
        attnT = self.g.op("Transpose", [attn], perm=[0, 1, 3, 2])
        xv = self.g.op("MatMul", [v, attnT])
        shp = self.g.const(np.array([1, C, H, W], np.int64))
        xv = self.g.op("Reshape", [xv, shp])
        pe, _ = self.conv(c["pe"], self.g.op("Reshape", [v, shp]), shape)  # 위치 인코딩
        y = self.g.op("Add", [xv, pe])
        return self.conv(c["proj"], y, shape)

    def psablock(self, m, x, shape):
        c = children(m)
        a, _ = self.attention(c["attn"], x, shape)
        x = self.g.op("Add", [x, a]) if m.add else a
        f, _ = self.seq(children(c["ffn"]).values(), x, shape)
        x = self.g.op("Add", [x, f]) if m.add else f
        return x, shape

    # ---- C2PSA : cv1 → (a, b) 분할 → b 에 PSA 블록 → concat → cv2 ---------------
    def c2psa(self, m, x, shape):
        c = children(m)
        y, s = self.conv(c["cv1"], x, shape)
        a, b = self.g.split(y, [m.c, m.c])
        b, _ = self.seq(children(c["m"]).values(), b, (m.c, s[1], s[2]))
        cat = self.g.op("Concat", [a, b], axis=1)
        return self.conv(c["cv2"], cat, s)

    # ---- Classify : conv → 전역평균풀링 → Linear → softmax ------------------------
    def classify(self, m, x, shape):
        c = children(m)
        y, s = self.conv(c["conv"], x, shape)
        y = self.g.op("GlobalAveragePool", [y])
        y = self.g.op("Flatten", [y], axis=1)
        t = tensors(c["linear"])
        y = self.g.op("Gemm", [y, self.g.const(t["weight"].astype(np.float32)),
                               self.g.const(t["bias"].astype(np.float32))], transB=1)
        return self.g.op("Softmax", [y], axis=1), (t["weight"].shape[0],)

    def module(self, m, x, shape):
        k = kind(m)
        fn = {"Conv": self.conv, "C2f": self.c2f, "C3k2": self.c2f, "C3k": self.c3,
              "Bottleneck": self.bottleneck, "C2PSA": self.c2psa, "PSABlock": self.psablock,
              "Classify": self.classify}.get(k)
        if fn is None:
            raise NotImplementedError(f"지원하지 않는 블록: {k}")
        return fn(m, x, shape)


def convert(pt_path, out_path, labels=None, imgsz=224):
    ck = load_pt(pt_path)
    model = ck.get("ema") or ck["model"]
    layers = list(children(children(model)["model"]).values())
    for L in layers:
        if getattr(L, "f", -1) != -1:
            raise NotImplementedError("순차 구조가 아닌 모델(검출 등)은 이 변환기 대상이 아닙니다")

    cv = Converter()
    y, shape = cv.seq(layers, "images", (3, imgsz, imgsz))
    cv.g.nodes.append(helper.make_node("Identity", [y], ["output0"]))
    nc = shape[0]

    graph = helper.make_graph(
        cv.g.nodes, Path(pt_path).stem,
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, imgsz, imgsz])],
        [helper.make_tensor_value_info("output0", TensorProto.FLOAT, [1, nc])], cv.g.inits)
    om = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)],
                           producer_name="pt2onnx_cls (no-torch)")
    om.ir_version = 8
    names = labels if labels and len(labels) == nc else [model.names[i] for i in range(nc)]
    meta = {"author": "Ultralytics", "task": "classify", "imgsz": str([imgsz, imgsz]), "batch": "1",
            "names": str({i: n for i, n in enumerate(names)}),
            "description": f"Converted from {Path(pt_path).name} (ultralytics {ck.get('version')}) without PyTorch"}
    for k, v in meta.items():
        e = om.metadata_props.add()
        e.key, e.value = k, v
    onnx.checker.check_model(om)
    onnx.save(om, out_path)
    return out_path, nc, len(cv.g.nodes)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pt")
    ap.add_argument("-o", "--out")
    ap.add_argument("--labels", help="사람이 읽는 클래스 이름 JSON 목록 (ImageNet 1000개)")
    a = ap.parse_args()
    labels = json.load(open(a.labels)) if a.labels else None
    out = a.out or str(Path(a.pt).with_suffix(".onnx"))
    path, nc, nn = convert(a.pt, out, labels)
    print(f"[완료] {path}  (클래스 {nc}개, 노드 {nn}개, {Path(path).stat().st_size / 1e6:.1f} MB)")
