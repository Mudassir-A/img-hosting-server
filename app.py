import os
import shutil
import uuid
import sqlite3

import uvicorn

from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Image Hosting Server")
app.mount("/images", StaticFiles(directory="images"), name="images")


def init_db():
    conn = sqlite3.connect("images.db")
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS images (id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL, original_name TEXT NOT NULL, UNIQUE(name))"
    )
    conn.commit()
    conn.close()


def init_directories():
    Path("images").mkdir(exist_ok=True)


init_db()
init_directories()


def get_db():
    return sqlite3.connect("images.db")


@app.post("/upload")
async def upload_image(file: UploadFile = File(...), custom_name: str = None):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=404, detail="File must be an image")
    orig_name = Path(file.filename).stem
    ext = Path(file.filename).suffix
    name = custom_name if custom_name else orig_name
    id_ = str(uuid.uuid4())
    path_ = f"images/{name}{ext}"

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM images WHERE name=?", (name,))
        if cur.fetchone():
            conn.close()
            raise HTTPException(
                status_code=400, detail=f"An image with name '{name}' already exists"
            )
        with open(path_, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        cur.execute(
            "INSERT INTO images (id, name, path, original_name) VALUES (?,?,?,?)",
            (id_, name, path_, orig_name),
        )
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=400, detail=f"An image with name '{name}' already exists"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_image/{identifier}")
async def get_image(identifier: str, by: str = "id"):
    conn = get_db()
    curr = conn.cursor()
    if by not in ["id", "name"]:
        raise HTTPException(
            status_code=400, detail=f"'by' parameter must be either 'id' or 'name'"
        )
    curr.execute(f"SELECT path FROM images WHERE {by}=?", (identifier,))
    res = curr.fetchone()
    conn.close()

    if not res:
        raise HTTPException(
            status_code=404, detail=f"Image not found with {by} '{identifier}'"
        )
    if not os.path.exists(res[0]):
        raise HTTPException(status_code=404, detail="Image file not found")
    return FileResponse(res[0])


@app.delete("/delete/{image_id}")
async def delete_image(image_id: str):
    conn = get_db()
    curr = conn.cursor()
    curr.execute("SELECT path FROM images WHERE id=?", (image_id,))
    res = curr.fetchone()
    if not res:
        conn.close()
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        curr.execute("DELETE FROM images WHERE id=?", (image_id,))
        conn.commit()
        if os.path.exists(res[0]):
            os.remove(res[0])
        return {"message": "Image deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/images")
async def list_images():
    conn = get_db()
    curr = conn.cursor()
    curr.execute("SELECT id,name,path,original_name FROM images")
    data = [
        {"id": r[0], "name": r[1], "path": r[2], "original_name": r[3]}
        for r in curr.fetchall()
    ]
    conn.close()
    return data


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=5600, reload=True)
