from pydantic import BaseModel


class HealthResponse(BaseModel):
    service: str
    status: str
    environment: str
    database: str
    artifactDir: str
    llmProvider: str
    llmModel: str
    sandboxProvider: str
