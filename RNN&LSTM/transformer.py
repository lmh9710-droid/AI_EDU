import torch
import torch.nn as nn

class SimpleTransformer(nn.Module):
    def __init__(self, src_vocab_size, tgt_vocab_size, d_model, nhead, num_layers):
        super(SimpleTransformer, self).__init__()

        self.src_embedding = nn.Embedding(src_vocab_size, d_model)
        self.tgt_embedding = nn.Embedding(tgt_vocab_size, d_model)

        self.transformer = nn.Transformer(
            d_model = d_model,
            nhead=nhead,
            num_encoder_layers= num_layers,
            num_decoder_layers= num_layers,
            batch_first= True
        )

        self.fc_out = nn.Linear(d_model, tgt_vocab_size)

    def forward(self, src, tgt, src_mask = None, tgt_mask = None):
        src_emb = self.src_embedding(src)
        tgt_emb = self.tgt_embedding(tgt)

        out = self.transformer(src_emb, tgt_emb, src_mask=src_mask, tgt_mask = tgt_mask)
        print("src_emb shape:", src_emb.shape)
        print("out shape:", out.shape)
        return self.fc_out(out)

model = SimpleTransformer(src_vocab_size= 100, tgt_vocab_size= 100, d_model =32, nhead =4, num_layers=3)
src =torch.randint(0, 100, (1, 10))
tgt = torch.randint(0, 100, (1, 10))

output = model(src, tgt)
print("output shape:", output.shape)
