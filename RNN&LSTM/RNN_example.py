import copy  # 가장 성능이 좋았던 모델의 가중치를 별도로 복사할 때 사용

import numpy as np  # 데이터 생성, 배열 연산, 오차 계산에 사용
import torch  # 텐서 연산과 딥러닝 학습에 사용
from torch import nn  # RNN, Linear 등의 신경망 구성 요소
from torch.utils.data import DataLoader, TensorDataset


# 난수의 시작값(seed)을 고정해 실행 결과의 재현성을 높입니다.
# 단, 실행 환경이나 라이브러리 버전이 다르면 결과가 달라질 수 있습니다.
np.random.seed(42)
torch.manual_seed(42)

# PyTorch의 CPU 연산에 사용하는 스레드 수를 1개로 설정합니다.
# 난수 고정과는 별개의 실행 설정입니다.
torch.set_num_threads(1)


# --------------------------------------------------
# 1. 실습용 데이터 생성
# 목표: 최근 10일의 [온도, 습도, 풍속]으로 다음 날 온도 예측
# --------------------------------------------------

# NumPy의 독립적인 난수 생성기입니다.
# 아래 데이터 생성에는 np.random.seed 대신 이 생성기의 seed가 적용됩니다.
rng = np.random.default_rng(42)

# 0일부터 1199일까지, 총 1200일을 나타내는 배열입니다.
days = np.arange(1200)

# 온도 = 기준 온도 + 60일 주기의 변화 + 무작위 잡음
# sin 함수는 반복되는 변화를 만들고,
# normal(평균, 표준편차, 개수)은 정규분포를 따르는 잡음을 만듭니다.
temperature = (
    20
    + 8 * np.sin(2 * np.pi * days / 60)
    + rng.normal(0, 0.5, len(days))
)

# 습도는 온도와 반대 방향으로 움직이는 경향을 주었습니다.
# 실제 관측 자료가 아니라 학습을 위한 인공 데이터입니다.
humidity = (
    60
    - 15 * np.sin(2 * np.pi * days / 60)
    + rng.normal(0, 2, len(days))
)

# 풍속은 15일 주기로 변하도록 만듭니다.
wind = (
    3
    + np.sin(2 * np.pi * days / 15)
    + rng.normal(0, 0.3, len(days))
)

# 세 배열을 열 방향으로 합칩니다.
# 한 행은 하루, 각 열은 순서대로 [온도, 습도, 풍속]입니다.
# data.shape: (1200, 3)
# float32는 신경망 학습에서 일반적으로 사용하는 실수 자료형입니다.
data = np.column_stack(
    [temperature, humidity, wind]
).astype(np.float32)

# 시간 순서대로 훈련 70%, 검증 15%, 테스트 15%를 나눕니다.
# 훈련: 모델의 가중치를 학습하는 데 사용
# 검증: 학습 중 가장 좋은 모델을 선택하는 데 사용
# 테스트: 선택이 끝난 모델의 최종 성능을 평가하는 데 사용
train_end = int(len(data) * 0.70)  # 840
val_end = int(len(data) * 0.85)    # 1020

# 특징마다 값의 크기가 다르므로 표준화합니다.
# axis=0은 날짜 방향으로 계산하여 각 특징의 평균과 표준편차를 구합니다.
# mean과 std의 모양은 각각 (3,)입니다.
#
# 미래 데이터의 정보가 학습에 들어가지 않도록,
# 평균과 표준편차는 반드시 훈련 구간에서만 계산합니다.
mean = data[:train_end].mean(axis=0)
std = data[:train_end].std(axis=0)

# 표준화 공식: (원래 값 - 평균) / 표준편차
# 훈련 구간에서 구한 동일한 기준을 모든 구간에 적용합니다.
# 따라서 훈련 구간의 각 특징은 평균 약 0, 표준편차 약 1이 됩니다.
scaled = (data - mean) / std


# --------------------------------------------------
# 2. 최근 10일 → 다음 날 온도 형태로 변환
# --------------------------------------------------

# 한 번의 예측에 사용할 과거 날짜 수입니다.
SEQ_LEN = 10

X, y, target_days = [], [], []

# target_day는 "온도를 예측할 날짜"입니다.
# 처음 10일은 과거 입력을 구성하는 데 필요하므로 10부터 시작합니다.
for target_day in range(SEQ_LEN, len(data)):
    # 예: target_day가 10이면 0~9일의 세 가지 특징을 입력으로 사용합니다.
    # 슬라이싱에서 끝 인덱스인 target_day는 포함되지 않습니다.
    # 입력 한 개의 모양: (10일, 3개 특징)
    X.append(scaled[target_day - SEQ_LEN:target_day])

    # 예측할 날짜의 온도만 정답으로 저장합니다.
    # 0번 열이 온도이며, 현재 값은 표준화된 온도입니다.
    y.append(scaled[target_day, 0])

    # 이후 훈련/검증/테스트를 나눌 때 사용할 날짜 정보입니다.
    target_days.append(target_day)

# 1190개의 입력 샘플을 하나의 배열로 쌓은 뒤 텐서로 변환합니다.
# X.shape: (1190, 10, 3)
# 차원 의미: [샘플 수, 날짜 수, 특징 수]
X = torch.tensor(np.stack(X), dtype=torch.float32)

# y는 처음에는 (1190,) 모양입니다.
# unsqueeze(1)로 두 번째 차원을 추가해 (1190, 1)로 만듭니다.
# 모델의 출력 모양과 정답의 모양을 맞추기 위한 처리입니다.
y = torch.tensor(y, dtype=torch.float32).unsqueeze(1)
target_days = np.array(target_days)

# 정답 날짜를 기준으로 각 샘플이 속할 구간을 결정합니다.
# 마스크는 조건을 만족하는 위치가 True인 배열입니다.
train_mask = torch.from_numpy(target_days < train_end)
val_mask = torch.from_numpy(
    (target_days >= train_end) & (target_days < val_end)
)
test_mask = torch.from_numpy(target_days >= val_end)

# True인 위치의 샘플만 선택합니다.
# 훈련 830개, 검증 180개, 테스트 180개가 됩니다.
# 처음 10일은 입력 구성에 사용되어 훈련 정답 개수에서 빠집니다.
#
# 검증/테스트 구간의 첫 샘플은 이전 구간의 관측값을 입력으로 쓸 수 있습니다.
# 각 예측 날짜보다 앞선 실제 관측값만 사용하는, 다음 날 예측 방식입니다.
X_train, y_train = X[train_mask], y[train_mask]
X_val, y_val = X[val_mask], y[val_mask]
X_test, y_test = X[test_mask], y[test_mask]

# TensorDataset은 입력과 정답을 한 쌍으로 묶습니다.
# DataLoader는 이 쌍들을 최대 64개씩 꺼내 학습에 공급합니다.
train_loader = DataLoader(
    TensorDataset(X_train, y_train),
    batch_size=64,
    shuffle=True,
)

# shuffle=True는 샘플들의 순서만 섞습니다.
# 각 샘플 내부의 10일 순서는 유지되므로 시간 흐름이 깨지지 않습니다.
print("훈련 입력:", tuple(X_train.shape))  # (830, 10, 3)
print("훈련 정답:", tuple(y_train.shape))  # (830, 1)


# --------------------------------------------------
# 3. RNN 모델 정의
# --------------------------------------------------

class TemperatureRNN(nn.Module):
    def __init__(self):
        # 부모 클래스의 초기화 함수를 호출해 신경망의 기본 기능을 준비합니다.
        super().__init__()

        # RNN은 하루씩 입력을 읽으면서 은닉 상태(hidden state)를 갱신합니다.
        # 은닉 상태는 이전 날짜들에서 얻은 정보를 담는 내부 벡터입니다.
        self.rnn = nn.RNN(
            input_size=3,      # 하루에 입력되는 특징: 온도, 습도, 풍속
            hidden_size=20,    # 은닉 상태를 구성하는 숫자의 개수
            num_layers=1,      # RNN 층을 한 겹 사용
            batch_first=True, # 입력 차원 순서: [배치, 시간, 특징]
        )

        # 마지막 은닉 상태의 20개 값을 온도 예측값 1개로 변환합니다.
        self.fc = nn.Linear(20, 1)

    def forward(self, x):
        # forward는 입력으로부터 예측값을 계산하는 과정을 정의합니다.
        # model(x)를 호출하면 이 함수가 실행됩니다.
        #
        # x.shape: [배치 크기, 10, 3]
        # 초기 은닉 상태를 전달하지 않으면 0으로 시작합니다.
        # 이 코드에서는 이전 배치의 은닉 상태를 다음 배치로 넘기지 않습니다.
        output, hidden = self.rnn(x)

        # output은 각 날짜를 처리한 뒤의 은닉 상태들을 담습니다.
        # output.shape: [배치 크기, 10, 20]
        #
        # hidden은 각 RNN 층의 마지막 은닉 상태입니다.
        # hidden.shape: [레이어 수, 배치 크기, 20]
        # 여기서는 output에서 마지막 시점의 값을 꺼내므로 hidden은 쓰지 않습니다.

        # ':'는 모든 샘플, '-1'은 마지막 날짜, 마지막 ':'는 모든 은닉 값을 뜻합니다.
        # 최근 10일을 모두 처리한 상태를 예측에 사용합니다.
        last_hidden = output[:, -1, :]  # [배치 크기, 20]

        # 출력은 아직 실제 °C가 아니라 표준화된 온도입니다.
        prediction = self.fc(last_hidden)  # [배치 크기, 1]
        return prediction


model = TemperatureRNN()

# MSE: 예측값과 정답의 차이를 제곱한 뒤 평균한 값입니다.
# 큰 오차에 더 큰 벌점을 주며, 학습에서는 이 값을 줄입니다.
criterion = nn.MSELoss()

# Adam은 계산된 기울기를 이용해 모델의 가중치를 갱신합니다.
# lr은 한 번 갱신할 때의 변화 크기를 조절하는 학습률입니다.
optimizer = torch.optim.Adam(model.parameters(), lr=0.001)


# --------------------------------------------------
# 4. 모델 학습
# --------------------------------------------------

# 처음에는 검증 오차를 무한대로 두어 첫 결과가 저장되도록 합니다.
best_val_loss = float("inf")
best_state = None

# epoch 1회는 전체 훈련 데이터를 한 번 학습하는 과정입니다.
# range의 끝값은 포함되지 않으므로 총 60회 학습합니다.
for epoch in range(1, 61):
    # 모델을 학습 모드로 설정합니다.
    # train() 자체가 학습을 수행하는 것은 아닙니다.
    model.train()
    total_loss = 0.0

    for batch_X, batch_y in train_loader:
        # PyTorch는 기울기를 누적하므로 이전 배치의 기울기를 먼저 지웁니다.
        optimizer.zero_grad()

        # ① 순전파: 현재 가중치로 예측값을 구합니다.
        prediction = model(batch_X)

        # ② 손실 계산: 예측과 정답이 얼마나 다른지 측정합니다.
        loss = criterion(prediction, batch_y)

        # ③ 역전파: 손실을 줄이려면 각 가중치를 어떻게 바꿔야 하는지 계산합니다.
        # RNN에서는 시간 흐름을 거슬러 기울기를 계산하므로 BPTT라고 합니다.
        loss.backward()

        # 기울기 전체의 노름이 1.0을 넘으면 크기를 줄입니다.
        # RNN 학습에서 기울기가 지나치게 커지는 현상을 완화합니다.
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

        # ④ 가중치 갱신: 계산한 기울기를 바탕으로 모델을 수정합니다.
        optimizer.step()

        # loss는 배치의 평균 오차이므로 샘플 수를 곱해 합산합니다.
        # 이렇게 해야 마지막 배치의 크기가 작아도 전체 평균을 올바르게 구합니다.
        # item()은 텐서에 들어 있는 숫자를 Python 숫자로 꺼냅니다.
        total_loss += loss.item() * len(batch_X)

    train_loss = total_loss / len(X_train)

    # 매 epoch가 끝나면 검증 데이터로 성능을 확인합니다.
    model.eval()

    # 검증에서는 가중치를 바꾸지 않으므로 기울기 계산을 생략합니다.
    # eval()과 no_grad()는 역할이 다르므로 함께 사용합니다.
    with torch.no_grad():
        val_loss = criterion(model(X_val), y_val).item()

    # 지금까지 가장 낮은 검증 오차를 기록했다면 모델 상태를 저장합니다.
    if val_loss < best_val_loss:
        best_val_loss = val_loss

        # state_dict에는 모델의 가중치 등이 들어 있습니다.
        # 이후 학습으로 저장된 값까지 바뀌지 않도록 깊은 복사를 합니다.
        best_state = copy.deepcopy(model.state_dict())

    # 첫 epoch와 10의 배수 epoch에서 진행 상황을 출력합니다.
    # 여기서 MSE는 표준화된 온도를 기준으로 계산한 값입니다.
    if epoch == 1 or epoch % 10 == 0:
        print(
            f"Epoch {epoch:02d} | "
            f"훈련 MSE: {train_loss:.4f} | "
            f"검증 MSE: {val_loss:.4f}"
        )


# --------------------------------------------------
# 5. 테스트 평가: 실제 온도 단위로 복원
# --------------------------------------------------

# 마지막 epoch의 모델이 아니라 검증 성능이 가장 좋았던 모델을 불러옵니다.
model.load_state_dict(best_state)
model.eval()

with torch.no_grad():
    # 모델 출력: [테스트 샘플 수, 1]
    # squeeze(1): 크기가 1인 두 번째 차원을 제거 → [테스트 샘플 수]
    # numpy(): 오차 계산을 위해 NumPy 배열로 변환
    # 이 코드는 모델과 텐서가 CPU에 있으므로 바로 변환할 수 있습니다.
    prediction_scaled = model(X_test).squeeze(1).numpy()

# 표준화의 역연산으로 실제 온도 단위를 복원합니다.
# 원래 값 = 표준화된 값 × 표준편차 + 평균
# 0번 특징이 온도이므로 std[0], mean[0]을 사용합니다.
prediction_temp = prediction_scaled * std[0] + mean[0]
actual_temp = y_test.squeeze(1).numpy() * std[0] + mean[0]

# 비교 기준: "다음 날 온도는 마지막으로 관측한 온도와 같다"고 예측합니다.
# X_test[:, -1, 0]:
# 모든 테스트 샘플에서 마지막 날짜(-1)의 온도(0번 특징)를 선택합니다.
# RNN이 이 단순한 예측보다 좋은지 비교하기 위한 기준입니다.
baseline_temp = X_test[:, -1, 0].numpy() * std[0] + mean[0]

# MAE: 예측과 실제 값의 차이에 절댓값을 취한 뒤 평균합니다.
# 실제 온도로 복원한 뒤 계산하므로 단위는 °C입니다.
# 예를 들어 MAE가 0.5라면 평균적으로 약 0.5°C의 오차가 있다는 뜻입니다.
rnn_mae = np.mean(np.abs(prediction_temp - actual_temp))
baseline_mae = np.mean(np.abs(baseline_temp - actual_temp))

print(f"\nRNN 평균 절대 오차: {rnn_mae:.3f} °C")
print(f"단순 기준 평균 절대 오차: {baseline_mae:.3f} °C")

# 테스트 데이터의 처음 10개 결과를 실제 값과 나란히 보여 줍니다.
# zip은 두 배열에서 같은 위치에 있는 값을 한 쌍씩 꺼냅니다.
print("\n실제 온도와 예측 온도 비교")
for actual, predicted in zip(actual_temp[:10], prediction_temp[:10]):
    print(f"실제: {actual:6.2f} °C | 예측: {predicted:6.2f} °C")
