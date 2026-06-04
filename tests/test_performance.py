import time, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models import Base


@pytest.fixture(scope="module")
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_ingest_throughput(db_session):
    from backend.models import Source, SourceStream, SourceType
    source = Source(name="Bench Source", type=SourceType.M3U_URL, url="http://bench.m3u")
    db_session.add(source)
    db_session.commit()
    count = 500
    start = time.time()
    for i in range(count):
        stream = SourceStream(source_id=source.id, name=f"Channel {i}", url=f"http://stream-{i}.ts", group="Bench", tvg_id=f"ch{i}")
        db_session.add(stream)
    db_session.commit()
    elapsed = time.time() - start
    rate = count / elapsed if elapsed > 0 else 0
    streams = db_session.query(SourceStream).filter(SourceStream.source_id == source.id).count()
    assert streams == count
    assert rate > 100


def test_m3u_parse_speed():
    from backend.utils.m3u_parser import parse_m3u
    lines = ["#EXTM3U"]
    for i in range(2500):
        lines.append(f'#EXTINF:-1 tvg-id="ch{i}" group-title="Test",Channel {i}')
        lines.append(f'http://stream-{i}.ts')
    content = "\n".join(lines)
    start = time.time()
    streams, stats = parse_m3u(content)
    elapsed = time.time() - start
    assert stats["parsed"] == 2500
    assert elapsed < 0.5
