from cairntir.memory import embeddings
embeddings.production_embedding_provider = lambda: embeddings.HashEmbeddingProvider(dimension=16)
import cairntir.cli as cli
cli.production_embedding_provider = embeddings.production_embedding_provider
