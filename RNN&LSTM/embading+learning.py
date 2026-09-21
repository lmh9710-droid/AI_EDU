import torch
from torch import nn
from torch.nn.utils.rnn import pad_sequence, pack_padded_sequence

torch.manual_seed(42)

# 작은 데이터이므로 CPU로 실습합니다.
train_data = [
    ("영화가 정말 재미있다", 1),
    ("영화가 정말 좋다", 1),
    ("스토리가 정말 좋다", 1),
    ("배우의 연기가 훌륭하다", 1),
    ("음악이 정말 좋다", 1),
    ("결말이 정말 감동적이다", 1),
    ("다시 보고 싶다", 1),
    ("정말 추천하고 싶다", 1),
    ("지루하지 않고 재미있다", 1),
    ("기대보다 훨씬 좋다", 1),
    ("스토리가 좋고 연기도 좋다", 1),
    ("정말 좋은 영화다", 1),

    ("영화가 정말 지루하다", 0),
    ("영화가 정말 별로다", 0),
    ("스토리가 정말 별로다", 0),
    ("배우의 연기가 어색하다", 0),
    ("음악이 정말 별로다", 0),
    ("결말이 정말 실망스럽다", 0),
    ("다시 보고 싶지 않다", 0),
    ("정말 추천하고 싶지 않다", 0),
    ("재미있지 않고 지루하다", 0),
    ("기대보다 훨씬 별로다", 0),
    ("스토리가 나쁘고 연기도 별로다", 0),
    ("정말 나쁜 영화다", 0),
]

# 특수 토큰
PAD_ID = 0
UNK_ID = 1

vocab = {
    "<PAD>": PAD_ID,
    "<UNK>": UNK_ID,
}

def tokenize(text):
    return text.split()

for text, _ in train_data:
    for token in tokenize(text):
        if token not in vocab:
            vocab[token] = len(vocab)

def encode(text):
    tokens = tokenize(text)

    if not tokens:
        raise ValueError("한 단어 이상 입력해 주세요.")

    return torch.tensor(
        [vocab.get(token, UNK_ID) for token in tokens],
        dtype=torch.long,
    )

def make_batch(texts):
    sequences = [encode(text) for text in texts]

    # 패딩을 추가하기 전의 실제 문장 길이
    lengths = torch.tensor(
        [len(sequence) for sequence in sequences],
        dtype=torch.long,
    )

    # 배치에서 가장 긴 문장에 맞춰 뒤쪽에 패딩 추가
    input_ids = pad_sequence(
        sequences,
        batch_first=True,
        padding_value=PAD_ID,
    )

    return input_ids, lengths

train_texts = [text for text, _ in train_data]

labels = torch.tensor(
    [label for _, label in train_data],
    dtype=torch.float32,
)

input_ids, lengths = make_batch(train_texts)

print("사전 크기:", len(vocab))
print("입력 모양:", tuple(input_ids.shape))
print("정답 모양:", tuple(labels.shape))
print("첫 문장 ID:", encode(train_texts[0]).tolist())

class SentimentLSTM(nn.Module):
    def __init__(self, vocab_size, embedding_dim=32, hidden_size=32):
        super().__init__()

        self.embedding = nn.Embedding(
            num_embeddings=vocab_size,
            embedding_dim=embedding_dim,
            padding_idx=PAD_ID,
        )

        self.lstm = nn.LSTM(
            input_size=embedding_dim,
            hidden_size=hidden_size,
            num_layers=1,
            batch_first=True,
        )

        self.classifier = nn.Linear(hidden_size, 1)

    def forward(self, input_ids, lengths):
        # input_ids: [배치, 최대 문장 길이]
        embedded = self.embedding(input_ids)

        # embedded: [배치, 최대 문장 길이, 32]
        packed = pack_padded_sequence(
            embedded,
            lengths.cpu(),
            batch_first=True,
            enforce_sorted=False,
        )

        _, (h_n, c_n) = self.lstm(packed)

        # 단층·단방향 LSTM에서 h_n: [1, 배치, 32]
        # 각 문장의 실제 끝에 해당하는 은닉 상태
        sentence_vector = h_n[-1]  # [배치, 32]

        logits = self.classifier(sentence_vector)  # [배치, 1]

        return logits.squeeze(-1)  # [배치]


model = SentimentLSTM(vocab_size=len(vocab))

print(model)

criterion = nn.BCEWithLogitsLoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

# 데이터가 24개뿐이므로 전체를 한 배치로 학습합니다.
for epoch in range(1, 151):
    model.train()

    optimizer.zero_grad()

    logits = model(input_ids, lengths)
    loss = criterion(logits, labels)

    loss.backward()

    nn.utils.clip_grad_norm_(
        model.parameters(),
        max_norm=1.0,
    )

    optimizer.step()

    if epoch == 1 or epoch % 25 == 0:
        model.eval()

        with torch.no_grad():
            eval_logits = model(input_ids, lengths)
            probabilities = torch.sigmoid(eval_logits)
            predictions = (probabilities >= 0.5).float()
            accuracy = (predictions == labels).float().mean()

        print(
            f"Epoch {epoch:03d} | "
            f"손실: {loss.item():.4f} | "
            f"훈련 정확도: {accuracy.item():.1%}"
        )

def predict(text):
    model.eval()

    batch_ids, batch_lengths = make_batch([text])

    with torch.no_grad():
        logit = model(batch_ids, batch_lengths)
        positive_score = torch.sigmoid(logit).item()

    tokens = tokenize(text)
    unknown_ratio = sum(
        token not in vocab for token in tokens
    ) / len(tokens)

    label = "긍정" if positive_score >= 0.5 else "부정"

    return label, positive_score, unknown_ratio


test_texts = [
    "연기가 정말 좋다",
    "결말이 정말 별로다",
    "영화가 좋지 않다",
    "정말 재미있어요",
    "음악이 좋고 결말이 실망스럽다",
]

for text in test_texts:
    label, score, unknown_ratio = predict(text)

    print(f"\n문장: {text}")
    print(f"예측: {label}")
    print(f"긍정 점수: {score:.3f}")
    print(f"모르는 토큰 비율: {unknown_ratio:.0%}")
