import uuid
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from fastapi import FastAPI, HTTPException, status, UploadFile, Depends

from .utils.aws import S3
from . import models, crud
from .database import SessionLocal, engine
from .utils.utils import is_valid_csv, required_csv_columns

load_dotenv()

models.Base.metadata.create_all(bind=engine)

app = FastAPI()


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/api/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_csv(file: UploadFile | None = None, db: Session = Depends(get_db)):
    """Upload a CSV file, validate it, create a request in db then process it using celery worker"""
    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No upload file sent",
        )

    if file.content_type != "text/csv":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File must be CSV",
        )
    if not is_valid_csv(file):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid CSV file, must have columns: {required_csv_columns}",
        )

    s3 = S3()
    request_id = uuid.uuid4()
    file_name = f"csv/original/{request_id}.csv"

    try:
        s3.upload_file(file.file, file_name)
        request = crud.create_request(db, request_id)
        return {"detail": "File uploaded, getting processed", "request_id": request.id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


@app.get("/api/status/{request_id}", status_code=status.HTTP_200_OK)
async def get_status(request_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get the status of a request"""
    try:
        request = crud.get_request(db, request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Request not found",
            )
        return request

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e
