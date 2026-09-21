import torch
from torch import nn

torch.manual_seed(42)

train_texts = [
    "영화가 정말 쓰레기다.",
    "영화가 정말 그지같다.",
    "정말 뭐 같다.",
]

vocab = {"<PAD>" :  0, "<UNK>": 1}

for text in train_texts:
    for token in text.split():
        if token not in vocab:
            vocab[token] = len(vocab)

def encode(text):
    return [
        vocab.get(token, vocab["<UNK>"])
        for token in text.split()
    ]

encoded = [encode(text) for text in train_texts]

lengths = torch.tensor([len(ids) for ids in encoded])

max_length = int(lengths.max().item())

padded = [
    ids+ [vocab["<PAD>"]] * (max_length - len(ids))
    for ids in encoded
]

input_ids = torch.tensor(padded, dtype=torch.long)

embedding = nn.Embedding(
    num_embeddings= len(vocab),
    embedding_dim= 4,
    padding_idx= vocab["<PAD>"],

)

vectors = embedding(input_ids)

print("사전:", vocab)
print("입력 ID:\n", input_ids)
print("실제 문장 길이:", lengths.tolist())
print("입력 모양:", tuple(input_ids.shape))
print("임베딩 결과 모양:", tuple(vectors.shape))
print("처음 보는 표현:", encode("영화가 ㅈ 같다."))
