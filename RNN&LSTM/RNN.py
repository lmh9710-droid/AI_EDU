import copy

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

np.random.seed(42)
torch.manual_seed(42)
torch.set_num_threads(1)

rng = np.random.default_rng(42)
days= np.arange(1200)

temperature = (
    20
    + 8 * np.sin(2 * np.pi *days / 60)
    + rng.normal(0, 0.5, len(days))
)

humidity = (
    60
    - 15 * np.sin(2 * np.pi * days / 60)
    + rng.normal(0, 2, len(days))
)


wind= (
    3
    + np.sin(2 * np.pi *days / 60)
    + rng.normal(0, 0.3, len(days))
)

data = np.column_stack(
    [temperature, humidity, wind]
).astype(np.float32)

train_end = int(len(data) * 0.70)
val_end = int(len(data) * 0.85)

mean = data[:train_end].mean(axis = 0)
std = data[:train_end].std(axis = 0)
scaled = (data-mean) / std

SEQ_LEN = 10

X, y, target_days = [], [], []

for target_day in range(SEQ_LEN, len(data)):
    X.append(scaled[target_day - SEQ_LEN:target_day])
    y.append(scaled[target_day, 0])
    target_days.append(target_day)
X = torch.tensor(np.stack(X), dtype=torch.float32)
y = torch.tensor(y, dtype=torch.float32).unsqueeze(1)
target_days =np.array(target_days)


train_mask = torch.from_numpy(target_days < train_end)
val_mask = torch.from_numpy(
    (target_days >= train_end) & (target_days < val_end)
)
test_mask = torch.from_numpy(target_days >= val_end)
X_train, y_train = X[train_mask], y[train_mask]
X_val, y_val = X[val_mask], y[val_mask]
X_test, y_test= X[test_mask], y[test_mask]

train_loader = DataLoader( 
    TensorDataset(X_train, y_train),
    batch_size = 64, 
    shuffle= True,
)

print("훈련 입력: ", tuple(X_train.shape))
print("훈련 정잡: ", tuple(y_train.shape))

#3 RNN 모델 정의
class TemperatureRNN( nn.Module):
    def __init__(self):
        super().__init__()

        self.rnn =  nn.RNN(
            input_size =3,
            hidden_size= 20,
            num_layers= 1,
            batch_first= True,
        )
        self.fc = nn.Linear(20, 1)

    def forward(self, x):
        output, hidden = self.rnn(x)

        last_hidden = output[:, -1, :]

        prediction = self.fc(last_hidden)
        return prediction 

model = TemperatureRNN()
criterion = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr = 0.001)

#4. 모델 학습 
best_val_loss = float("inf")
best_state = None

for epoch in range(1, 61):
    model.train()
    total_loss = 0.0

    for batch_X, batch_y in train_loader:
        optimizer.zero_grad()

        prediction = model(batch_X)
        loss = criterion(prediction, batch_y)

        loss.backward()

        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        total_loss += loss.item() * len(batch_X)

    train_loss = total_loss / len(X_train)

    model.eval()
    with torch.no_grad() :
        val_loss = criterion(model(X_val), y_val).item()

    if val_loss < best_val_loss:
        bset_val_loss = val_loss
        bset_state = copy.deepcopy(model.state_dict())

    if epoch == 1 or epoch % 10 == 0:
        print(
            f"Epoch {epoch: 02d} |"
            f"훈련 MSE: {train_loss: .4f} | "
            f"검증 MSE: {val_loss: .4f}"
        )


#5. 테스트 평가

model.load_state_dict(bset_state)
model.eval()

with torch.no_grad():
    prediction_scaled = model(X_test).squeeze(1).numpy()

prediction_temp = prediction_scaled * std[0] + mean[0]
actual_temp = y_test.squeeze(1).numpy() * std[0] + mean[0]

baseline_temp = X_test[:, -1, 0].numpy() * std[0] + mean[0]

rnn_mae= np.mean(np.abs(prediction_temp - actual_temp))
baseline_mae = np.mean(np.abs(baseline_temp - actual_temp))

print(f"\nRNN 평균 절대 오차: {rnn_mae: .3f} ℃")
print(f"단순 기준 평균 절대 오차: {baseline_mae: .3f} ℃")

print("\n 실제 온도와 예측 온도 비교")
for actual, predicted in zip(actual_temp[:10], prediction_temp[:10]):
   print(f"실제: {actual: 6.2f} ℃ | 예측: {predicted: 6.2f} ℃")
