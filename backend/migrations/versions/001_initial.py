"""Initial migration — core tables only."""
from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("url", sa.String(2048)),
        sa.Column("file_path", sa.String(1024)),
        sa.Column("auth_username", sa.String(255)),
        sa.Column("auth_password", sa.String(512)),
        sa.Column("auth_headers", sa.JSON),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("priority", sa.Integer, default=100),
        sa.Column("last_ingest", sa.DateTime),
        sa.Column("last_ingest_status", sa.String(20)),
        sa.Column("last_ingest_error", sa.Text),
        sa.Column("ingest_schedule", sa.String(100)),
        sa.Column("stream_count", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
        sa.Column("deleted_at", sa.DateTime),
    )
    op.create_index("ix_sources_enabled_priority", "sources", ["enabled", "priority"])

    op.create_table("canonical_channels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(500)),
        sa.Column("name_original", sa.String(500)),
        sa.Column("group", sa.String(255)),
        sa.Column("country", sa.String(2)),
        sa.Column("language", sa.String(50)),
        sa.Column("logo", sa.String(2048)),
        sa.Column("tvg_id", sa.String(255)),
        sa.Column("last_validation", sa.DateTime),
        sa.Column("validation_status", sa.String(20)),
        sa.Column("uptime_percent", sa.Float),
        sa.Column("preferred_source_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_index("ix_cc_status_group", "canonical_channels", ["validation_status", "group"])

    op.create_table("source_streams",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("canonical_channel_id", sa.String(36), sa.ForeignKey("canonical_channels.id")),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("group", sa.String(255)),
        sa.Column("tvg_id", sa.String(255)),
        sa.Column("tvg_name", sa.String(500)),
        sa.Column("logo", sa.String(2048)),
        sa.Column("duration", sa.Integer),
        sa.Column("extra_attributes", sa.JSON),
        sa.Column("deleted_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_index("ix_ss_source_canonical", "source_streams", ["source_id", "canonical_channel_id"])
    op.create_index("ix_ss_source_deleted", "source_streams", ["source_id", "deleted_at"])
    op.create_index("ix_ss_canonical", "source_streams", ["canonical_channel_id"])

    op.create_table("validation_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_stream_id", sa.String(36), sa.ForeignKey("source_streams.id"), nullable=False),
        sa.Column("checked_at", sa.DateTime, nullable=False),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("codec", sa.String(50)),
        sa.Column("resolution", sa.String(20)),
        sa.Column("bitrate", sa.Integer),
        sa.Column("audio_tracks", sa.Integer),
        sa.Column("response_time_ms", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("checker_tool", sa.String(20)),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_vr_stream_checked", "validation_records", ["source_stream_id", "checked_at"])

    op.create_table("output_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("included_sources", sa.JSON),
        sa.Column("include_dead_channels", sa.Boolean, default=False),
        sa.Column("min_uptime_percent", sa.Float, default=0.0),
        sa.Column("generate_schedule", sa.String(100)),
        sa.Column("last_generated", sa.DateTime),
        sa.Column("channel_count", sa.Integer, default=0),
        sa.Column("m3u_url_path", sa.String(255)),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
        sa.Column("deleted_at", sa.DateTime),
    )
    op.create_index("ix_op_enabled", "output_profiles", ["enabled"])

    op.create_table("task_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("message", sa.String(2000)),
        sa.Column("error_details", sa.Text),
        sa.Column("stats", sa.JSON),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_tl_name_started", "task_logs", ["task_name", "started_at"])
    op.create_index("ix_tl_completed", "task_logs", ["completed_at"])

    op.create_table("system_config",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("value", sa.JSON),
    )


def downgrade():
    op.drop_table("validation_records")
    op.drop_table("source_streams")
    op.drop_table("canonical_channels")
    op.drop_table("output_profiles")
    op.drop_table("task_logs")
    op.drop_table("system_config")
    op.drop_table("sources")
