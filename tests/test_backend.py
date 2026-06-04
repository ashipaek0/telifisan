import os, sys, tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent))
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


# ── Models ────────────────────────────────────────────────────

def test_create_source(db_session):
    from backend.models import Source, SourceType, IngestStatus
    s = Source(name="Test Source", type=SourceType.M3U_URL, url="http://example.com/playlist.m3u")
    db_session.add(s)
    db_session.commit()
    assert s.id is not None
    assert s.name == "Test Source"
    assert s.stream_count == 0


def test_create_canonical_channel(db_session):
    from backend.models import CanonicalChannel, ValidationStatus
    ch = CanonicalChannel(name="BBC One", name_original="BBC One HD", group="News")
    db_session.add(ch)
    db_session.commit()
    assert ch.validation_status == ValidationStatus.UNKNOWN


def test_source_stream_relationship(db_session):
    from backend.models import Source, SourceStream, SourceType
    s = Source(name="Src", type=SourceType.M3U_URL, url="http://example.com/playlist.m3u")
    db_session.add(s)
    db_session.commit()
    stream = SourceStream(source_id=s.id, name="BBC", url="http://example.com/stream")
    db_session.add(stream)
    db_session.commit()
    assert stream.source_id == s.id
    assert stream.source.name == "Src"


def test_output_profile_creation(db_session):
    from backend.models import OutputProfile, OutputMode
    p = OutputProfile(name="Test", mode=OutputMode.DIRECT, include_dead_channels=False)
    db_session.add(p)
    db_session.commit()
    assert p.id is not None
    assert p.enabled is True


# ── M3U Parser ────────────────────────────────────────────────

def test_parse_m3u_basic():
    from backend.utils.m3u_parser import parse_m3u
    content = """#EXTM3U
#EXTINF:-1 tvg-id="bbc1.uk" tvg-name="BBC One" group-title="News",BBC One HD
http://example.com/bbc1
#EXTINF:-1 tvg-id="cnn.us" group-title="News",CNN
http://example.com/cnn
"""
    streams, stats = parse_m3u(content)
    assert stats["parsed"] == 2
    assert stats["errors"] == 0
    assert streams[0]["name"] == "BBC One HD"
    assert streams[0]["tvg_id"] == "bbc1.uk"
    assert streams[0]["group"] == "News"
    assert streams[0]["url"] == "http://example.com/bbc1"
    assert streams[1]["name"] == "CNN"


def test_parse_m3u_malformed():
    from backend.utils.m3u_parser import parse_m3u
    content = """#EXTM3U
#EXTINF:-1,Bad Stream
not-a-url
#EXTINF:-1 tvg-id="ok.uk",OK Channel
http://example.com/ok
"""
    streams, stats = parse_m3u(content)
    assert stats["parsed"] == 1
    assert stats["errors"] >= 1


# ── Ingest ────────────────────────────────────────────────────

def test_ingest_creates_source_streams(db_session):
    from backend.models import Source, SourceStream, CanonicalChannel, SourceType
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

    streams = db_session.query(SourceStream).filter(
        SourceStream.source_id == source.id, SourceStream.deleted_at.is_(None),
    ).all()
    assert len(streams) == 3
    assert task_log.status.value == "SUCCESS"
    assert task_log.stats["new"] == 3


# ── Validation ────────────────────────────────────────────────

def test_http_head_check_unreachable():
    from backend.services.validation import _http_head_check
    reachable, head_ok = _http_head_check("http://localhost:19999/nonexistent", 2)
    assert reachable is False
    assert head_ok is False


# ── Output ────────────────────────────────────────────────────

def test_generate_m3u_basic(db_session):
    from backend.models import Source, SourceStream, CanonicalChannel, SourceType, OutputProfile, OutputMode
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


# ── Auth ──────────────────────────────────────────────────────

def test_api_key_generation():
    from backend.config import generate_api_key
    key = generate_api_key()
    assert len(key) >= 48
    assert isinstance(key, str)
