import hashlib

class HashService:
    CHUNK_SIZE = 64 * 1024  # 64KB

    @staticmethod
    def calculate_hash(file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(HashService.CHUNK_SIZE):
                sha256.update(chunk)
        return sha256.hexdigest()
