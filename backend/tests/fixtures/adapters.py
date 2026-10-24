import hashlib
import re

import numpy as np


class WordTokenizer:
    """Deterministic test tokenizer; production always uses the BGE tokenizer."""

    def __init__(self):
        self.vocab = {}
        self.words = {}

    def __call__(self, text, **kwargs):
        matches = list(re.finditer(r"\w+|[^\w\s]", text))
        ids = []
        for match in matches:
            word = match.group()
            if word not in self.vocab:
                self.vocab[word] = len(self.vocab)
                self.words[self.vocab[word]] = word
            ids.append(self.vocab[word])
        return {"input_ids": ids, "offset_mapping": [m.span() for m in matches]}

    def encode(self, text, **kwargs):
        return self(text)["input_ids"]

    def decode(self, ids, **kwargs):
        return " ".join(self.words[i] for i in ids)

    def convert_ids_to_tokens(self, token_id):
        return self.words[token_id]


class FakeEmbeddings:
    def __init__(self):
        self.tokenizer = WordTokenizer()

    def embed_documents(self, texts):
        vectors = np.zeros((len(texts), 384), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in text.casefold().split():
                vectors[row, int(hashlib.sha256(word.encode()).hexdigest(), 16) % 384] += 1
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    def embed_query(self, question):
        return self.embed_documents([question])[0]


class FakeReranker:
    def score(self, question, passages):
        return [
            float(len(set(question.lower().split()) & set(p.lower().split()))) for p in passages
        ]
