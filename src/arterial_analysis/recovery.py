"""Separate, atomic recovery copies; never overwrite the user's project."""
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone


def write_recovery(path, project, source):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as stream:
            temporary=Path(stream.name)
            json.dump(dict(saved_at=datetime.now(timezone.utc).isoformat(),source=source,project=project.to_dict()),stream,ensure_ascii=False)
            stream.flush();os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary:temporary.unlink(missing_ok=True)


def read_recovery(path):
    from .project import ArterialProject
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    return ArterialProject.from_dict(data['project']),data.get('source')
