import hashlib, json, base64
from pathlib import Path
from datetime import datetime
from loguru import logger
from app.mcp_client.base import MCPClientBase

MANIFEST_PATH = Path("_manifest.json")


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}

def save_manifest(manifest: dict):
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def sync_vault(
    materials: list,
    lms_client,
    obsidian_mcp_url: str,
    auth_code: str,
    progress_cb,
) -> dict:
    mcp = MCPClientBase(
        server_url=obsidian_mcp_url,
        headers={"Authorization": f"Bearer {auth_code}"},
    )

    tools = await mcp.list_tools()
    if "write_file" not in [t.name for t in tools]:
        raise RuntimeError("Obsidian MCP: write_file Tool 없음")

    manifest = load_manifest()
    saved = skipped = failed = 0
    total = len(materials)

    for i, material in enumerate(materials):
        key = f"{material['course_name']}/week{material['week']:02d}/{material['filename']}"

        try:
            file_data: bytes = await lms_client.download_file(material["url"])
        except Exception as e:
            failed += 1
            await progress_cb({
                "t": datetime.now().strftime("%H:%M"),
                "text": f"다운로드 실패: {material['filename']}",
                "kind": "sync", "meta": str(e)[:50],
                "current": i + 1, "total": total, "status": "error",
            })
            continue

        file_hash = sha256(file_data)

        if manifest.get(key) == file_hash:
            skipped += 1
            await progress_cb({
                "t": datetime.now().strftime("%H:%M"),
                "text": f"변경 없음: {material['filename']}",
                "kind": "sync",
                "meta": f"{material['course_name']} · Week {material['week']}",
                "current": i + 1, "total": total, "status": "skipped",
            })
            continue

        result = await mcp.call_tool("write_file", {
            "relative_path": key,
            "content": base64.b64encode(file_data).decode(),
            "mime_type": "application/octet-stream",
        })

        if result == "saved":
            manifest[key] = file_hash
            saved += 1
            await progress_cb({
                "t": datetime.now().strftime("%H:%M"),
                "text": f"Vault에 강의자료 저장: {material['filename']}",
                "kind": "sync",
                "meta": f"{material['course_name']} · Week {material['week']}",
                "current": i + 1, "total": total, "status": "saved",
            })
        else:
            failed += 1

    save_manifest(manifest)
    await progress_cb({
        "t": datetime.now().strftime("%H:%M"),
        "text": "Vault 동기화 완료",
        "kind": "cron",
        "meta": f"{saved}개 저장 · {skipped}개 변경없음 · {failed}개 실패",
        "current": total, "total": total, "status": "done",
    })

    return {"saved": saved, "skipped": skipped, "failed": failed}
