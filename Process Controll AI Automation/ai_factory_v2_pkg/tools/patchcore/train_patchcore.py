"""PatchCore 학습 + OpenVINO 변환 (anomalib 2.x). root 를 사진 폴더로 바꿔 실행: python train_patchcore.py"""
from anomalib.data import Folder
from anomalib.deploy import ExportType
from anomalib.engine import Engine
from anomalib.models import Patchcore

datamodule = Folder(
    name="bolt",
    root="/home/<사용자>/train/pc_data/bolt",   # ← 사진 폴더
    normal_dir="good", normal_test_dir="good_test", abnormal_dir="defect",
    train_batch_size=16, eval_batch_size=16, num_workers=4,   # WSL 에서 오류 나면 num_workers=0
)
model = Patchcore(backbone="wide_resnet50_2", layers=["layer2", "layer3"], coreset_sampling_ratio=0.1)
engine = Engine(default_root_dir="results")
engine.fit(datamodule=datamodule, model=model)
engine.test(datamodule=datamodule, model=model)
engine.export(model=model, export_type=ExportType.OPENVINO)   # → results/Patchcore/bolt/vN/weights/openvino/
