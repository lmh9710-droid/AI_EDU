"""
safe_pt.py : PyTorch 없이 Ultralytics .pt 를 '안전하게' 읽는 로더

  .pt = zip( data.pkl[모델 구조, 피클] + data/0,1,2...[가중치 원시 바이트] )
  - 피클이 참조하는 클래스를 화이트리스트로 제한 → 임의 코드 실행 차단
  - 모듈은 실제 클래스 대신 '속성만 담는 빈 껍데기(Stub)'로 복원
  - 텐서는 numpy 배열로 복원
"""
import pickle
import zipfile

import numpy as np

# 허용하는 (모듈, 클래스) 접두어. 이 외의 것은 전부 거부
ALLOWED_PREFIX = (
    "torch.nn.modules.", "ultralytics.nn.", "torchvision.transforms.",
    "collections.OrderedDict", "torch._utils._rebuild", "torch.", "__builtin__.set",
    "builtins.set", "ultralytics.utils.IterableSimpleNamespace", "argparse.Namespace",
    "__builtin__.getattr", "builtins.getattr", "numpy.", "_codecs.encode", "pathlib.",
)
DTYPES = {"FloatStorage": np.float32, "HalfStorage": np.float16, "LongStorage": np.int64,
          "IntStorage": np.int32, "BFloat16Storage": None, "ByteStorage": np.uint8,
          "BoolStorage": np.bool_, "DoubleStorage": np.float64}


class _StubMeta(type):
    # 클래스 속성 접근(예: InterpolationMode.BILINEAR) → 이름 문자열 반환
    def __getattr__(cls, item):
        return f"{cls.__name__}.{item}"


def make_stub(fullname):
    def __setstate__(self, state):
        if isinstance(state, tuple) and len(state) == 2:  # (dict, slotstate)
            state = {**(state[0] or {}), **(state[1] or {})}
        self.__dict__.update(state if isinstance(state, dict) else {"_state": state})

    def __init__(self, *a, **k):
        self._args, self._kwargs = a, k

    return _StubMeta(fullname.split(".")[-1], (), {
        "__setstate__": __setstate__, "__init__": __init__, "_type": fullname,
        "__repr__": lambda self: f"<{fullname}>"})


def _safe_getattr(obj, name, *default):
    """피클 안의 getattr 은 Stub(빈 껍데기) 객체의 일반 속성에만 허용.
    실제 객체에 getattr 을 허용하면 obj.__class__.__subclasses__() 같은 경로로
    시스템 명령까지 도달할 수 있으므로 차단한다."""
    if name.startswith("_") or not (isinstance(obj, _StubMeta) or type(obj).__class__ is _StubMeta):
        raise pickle.UnpicklingError(f"허용되지 않은 속성 접근 차단: {type(obj).__name__}.{name}")
    return getattr(obj, name, *default)


class SafeUnpickler(pickle.Unpickler):
    def __init__(self, f, zf, prefix):
        super().__init__(f)
        self.zf, self.prefix, self.stubs = zf, prefix, {}

    def find_class(self, module, name):
        full = f"{module}.{name}"
        if not full.startswith(ALLOWED_PREFIX):
            raise pickle.UnpicklingError(f"허용되지 않은 클래스 차단: {full}")
        if full in ("collections.OrderedDict",):
            import collections
            return collections.OrderedDict
        if full in ("__builtin__.set", "builtins.set"):
            return set
        if full in ("__builtin__.getattr", "builtins.getattr"):
            return _safe_getattr
        if full == "torch._utils._rebuild_tensor_v2":
            return self._rebuild_tensor
        if full == "torch._utils._rebuild_parameter":
            return lambda data, requires_grad, hooks: data
        if name.endswith("Storage"):
            return name  # persistent_load 에서 dtype 판별용 문자열
        return self.stubs.setdefault(full, make_stub(full))

    def persistent_load(self, pid):
        # ('storage', 저장형식, 키, 위치, 원소수)
        _, stype, key, _loc, _numel = pid
        stype = stype if isinstance(stype, str) else stype.__name__
        dt = DTYPES.get(stype)
        if dt is None:
            raise pickle.UnpicklingError(f"지원하지 않는 저장 형식: {stype}")
        raw = self.zf.read(f"{self.prefix}/data/{key}")
        return np.frombuffer(raw, dtype=dt)

    @staticmethod
    def _rebuild_tensor(storage, offset, size, stride, *rest):
        if len(size) == 0:
            return storage[offset].copy()
        itemsize = storage.itemsize
        return np.lib.stride_tricks.as_strided(
            storage[offset:], shape=tuple(size),
            strides=tuple(s * itemsize for s in stride)).copy()


def load_pt(path):
    zf = zipfile.ZipFile(path)
    pkl = next(n for n in zf.namelist() if n.endswith("data.pkl"))
    prefix = pkl.rsplit("/", 1)[0]
    with zf.open(pkl) as f:
        return SafeUnpickler(f, zf, prefix).load()


def children(m):
    """nn.Module 의 하위 모듈 (OrderedDict)"""
    return getattr(m, "_modules", {}) or {}


def tensors(m):
    """nn.Module 의 파라미터 + 버퍼"""
    d = {}
    d.update({k: v for k, v in (getattr(m, "_parameters", {}) or {}).items() if v is not None})
    d.update({k: v for k, v in (getattr(m, "_buffers", {}) or {}).items() if v is not None})
    return d
