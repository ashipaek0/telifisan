import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models import Base


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def _setup_source_and_ingest(db_session):
    from backend.models import Source, SourceType
    from backend.services.ingest import ingest_source
    source = Source(name="Test Source", type=SourceType.M3U_URL, url="http://localhost/test.m3u", priority=50)
    db_session.add(source)
    db_session.commit()

    import requests
    class MockResponse:
        status_code = 200
        text = """#EXTM3U
#EXTINF:-1 tvg-id="bbc1.uk" tvg-name="BBC One" group-title="News",BBC One HD
http://example.com/bbc1
#EXTINF:-1 tvg-id="cnn.us" tvg-name="CNN" group-title="News",CNN US
http://example.com/cnn
#EXTINF:-1 tvg-id="sky.uk" tvg-name="Sky Sports" group-title="Sports",Sky Sports HD
http://example.com/sky
"""
        @staticmethod
        def raise_for_status():
            pass
    original_get = requests.get
    requests.get = lambda url, **kwargs: MockResponse()
    try:
        task_log = ingest_source(source.id, db_session)
    finally:
        requests.get = original_get
    return source, task_log


def test_ingest_creates_source_streams(db_session):
    from backend.models import SourceStream, CanonicalChannel
    source, task_log = _setup_source_and_ingest(db_session)
    streams = db_session.query(SourceStream).filter(SourceStream.source_id == source.id, SourceStream.deleted_at.is_(None)).all()
    assert len(streams) == 3
    channels = db_session.query(CanonicalChannel).all()
    assert len(channels) == 3
    assert task_log.status.value == "SUCCESS"
    assert task_log.stats["new"] == 3


def test_ingest_links_to_canonical(db_session):
    from backend.models import SourceStream
    _setup_source_and_ingest(db_session)
    streams = db_session.query(SourceStream).filter(SourceStream.deleted_at.is_(None)).all()
    for s in streams:
        assert s.canonical_channel_id is not None


def test_second_ingest_updates_existing(db_session):
    from backend.models import SourceStream, CanonicalChannel
    source, _ = _setup_source_and_ingest(db_session)
    stream_count_before = db_session.query(SourceStream).filter(SourceStream.source_id == source.id, SourceStream.deleted_at.is_(None)).count()
    channel_count_before = db_session.query(CanonicalChannel).count()

    from backend.services.ingest import ingest_source
    import requests
    class MockResponse:
        status_code = 200
        text = """#EXTM3U
#EXTINF:-1 tvg-id="bbc1.uk" tvg-name="BBC One" group-title="News",BBC One HD
http://example.com/bbc1
"""
        @staticmethod
        def raise_for_status():
            pass
    original_get = requests.get
    requests.get = lambda url, **kwargs: MockResponse()
    try:
        task_log2 = ingest_source(source.id, db_session)
    finally:
        requests.get = original_get

    stream_count_after = db_session.query(SourceStream).filter(SourceStream.source_id == source.id, SourceStream.deleted_at.is_(None)).count()
    assert stream_count_after == 1
    assert task_log2.stats["deleted"] == 2
    assert db_session.query(CanonicalChannel).count() == channel_count_before


def test_output_generation(db_session):
    from backend.models import CanonicalChannel, SourceStream, Source, SourceType, OutputProfile, OutputMode
    from backend.services.output import _generate_m3u

    source = Source(name="Src", type=SourceType.M3U_URL, url="http://example.com/m3u")
    db_session.add(source)
    db_session.commit()

    ch = CanonicalChannel(name="BBC One", group="News")
    db_session.add(ch)
    db_session.commit()

    stream = SourceStream(source_id=source.id, canonical_channel_id=ch.id, name="BBC One", url="http://example.com/stream")
    db_session.add(stream)
    db_session.commit()

    profile = OutputProfile(name="Test", mode=OutputMode.DIRECT)
    db_session.add(profile)
    db_session.commit()

    m3u = _generate_m3u([(ch, stream)], profile)
    assert "#EXTM3U" in m3u
    assert "BBC One" in m3u
    assert stream.url in m3u
