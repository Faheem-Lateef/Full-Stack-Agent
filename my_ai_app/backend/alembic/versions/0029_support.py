"""Add isolated support workspaces and durable jobs.

Revision ID: 0029_support
Revises: 0028_agent_memory
"""

from alembic import op

revision = "0029_support"
down_revision = "0028_agent_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "\nCREATE TABLE support_workspaces (\n\tid UUID NOT NULL, \n\tname VARCHAR(120) NOT NULL, \n\ttone VARCHAR(500) NOT NULL, \n\tescalation VARCHAR(1000) NOT NULL, \n\tgeneration_limit INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE, \n\tCONSTRAINT support_workspaces_pkey PRIMARY KEY (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE support_audit (\n\tid UUID NOT NULL, \n\tworkspace_id UUID NOT NULL, \n\tactor_id UUID NOT NULL, \n\taction VARCHAR(80) NOT NULL, \n\ttarget_id UUID, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE, \n\tCONSTRAINT support_audit_pkey PRIMARY KEY (id), \n\tCONSTRAINT support_audit_workspace_id_fkey FOREIGN KEY(workspace_id) REFERENCES support_workspaces (id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute("CREATE INDEX support_audit_workspace_id_idx ON support_audit (workspace_id)")
    op.execute(
        "\nCREATE TABLE support_cases (\n\tid UUID NOT NULL, \n\tworkspace_id UUID NOT NULL, \n\tcreated_by UUID NOT NULL, \n\tquestion TEXT NOT NULL, \n\tstate VARCHAR(20) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE, \n\tCONSTRAINT support_cases_pkey PRIMARY KEY (id), \n\tCONSTRAINT support_cases_workspace_id_key UNIQUE (workspace_id, id), \n\tCONSTRAINT support_cases_workspace_id_fkey FOREIGN KEY(workspace_id) REFERENCES support_workspaces (id) ON DELETE CASCADE, \n\tCONSTRAINT support_cases_created_by_fkey FOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX support_cases_workspace_id_idx ON support_cases (workspace_id)")
    op.execute(
        "\nCREATE TABLE support_documents (\n\tid UUID NOT NULL, \n\tworkspace_id UUID NOT NULL, \n\ttitle VARCHAR(200) NOT NULL, \n\tfilename VARCHAR(200) NOT NULL, \n\tchecksum VARCHAR(64) NOT NULL, \n\toriginal BYTEA, \n\tsize INTEGER NOT NULL, \n\tstate VARCHAR(20) NOT NULL, \n\terror VARCHAR(500), \n\treplaces_id UUID, \n\tembedding_model VARCHAR(100), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE, \n\tCONSTRAINT support_documents_pkey PRIMARY KEY (id), \n\tCONSTRAINT support_documents_workspace_id_key UNIQUE (workspace_id, id), \n\tCONSTRAINT support_documents_workspace_id_fkey FOREIGN KEY(workspace_id) REFERENCES support_workspaces (id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute(
        "CREATE INDEX support_documents_workspace_id_idx ON support_documents (workspace_id)"
    )
    op.execute(
        "\nCREATE TABLE support_invitations (\n\tid UUID NOT NULL, \n\tworkspace_id UUID NOT NULL, \n\temail VARCHAR(320) NOT NULL, \n\trole VARCHAR(10) NOT NULL, \n\ttoken_hash VARCHAR(64) NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tconsumed BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE, \n\tCONSTRAINT support_invitations_pkey PRIMARY KEY (id), \n\tCONSTRAINT support_invitations_workspace_id_fkey FOREIGN KEY(workspace_id) REFERENCES support_workspaces (id) ON DELETE CASCADE, \n\tCONSTRAINT support_invitations_token_hash_key UNIQUE (token_hash)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX support_invitations_workspace_id_idx ON support_invitations (workspace_id)"
    )
    op.execute(
        "\nCREATE TABLE support_jobs (\n\tid UUID NOT NULL, \n\tworkspace_id UUID NOT NULL, \n\tactor_id UUID NOT NULL, \n\tkind VARCHAR(20) NOT NULL, \n\ttarget_id UUID NOT NULL, \n\trequest_key VARCHAR(100) NOT NULL, \n\tstate VARCHAR(20) NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\terror VARCHAR(500), \n\tusage JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE, \n\tCONSTRAINT support_jobs_pkey PRIMARY KEY (id), \n\tCONSTRAINT support_jobs_workspace_id_key UNIQUE (workspace_id, request_key), \n\tCONSTRAINT support_jobs_workspace_id_fkey FOREIGN KEY(workspace_id) REFERENCES support_workspaces (id) ON DELETE CASCADE, \n\tCONSTRAINT support_jobs_actor_id_fkey FOREIGN KEY(actor_id) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX support_jobs_state_idx ON support_jobs (state)")
    op.execute("CREATE INDEX support_jobs_workspace_id_idx ON support_jobs (workspace_id)")
    op.execute(
        "\nCREATE TABLE support_memberships (\n\tworkspace_id UUID NOT NULL, \n\tuser_id UUID NOT NULL, \n\trole VARCHAR(10) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE, \n\tCONSTRAINT support_memberships_pkey PRIMARY KEY (workspace_id, user_id), \n\tCONSTRAINT support_memberships_workspace_id_fkey FOREIGN KEY(workspace_id) REFERENCES support_workspaces (id) ON DELETE CASCADE, \n\tCONSTRAINT support_memberships_user_id_fkey FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE support_chunks (\n\tid UUID NOT NULL, \n\tworkspace_id UUID NOT NULL, \n\tdocument_id UUID NOT NULL, \n\tordinal INTEGER NOT NULL, \n\tpage INTEGER NOT NULL, \n\ttext TEXT NOT NULL, \n\tembedding JSONB, \n\tCONSTRAINT support_chunks_pkey PRIMARY KEY (id), \n\tCONSTRAINT support_chunks_workspace_id_fkey FOREIGN KEY(workspace_id, document_id) REFERENCES support_documents (workspace_id, id) ON DELETE CASCADE, \n\tCONSTRAINT support_chunks_document_id_key UNIQUE (document_id, ordinal)\n)\n\n"
    )
    op.execute("CREATE INDEX support_chunks_workspace_id_idx ON support_chunks (workspace_id)")
    op.execute(
        "\nCREATE TABLE support_drafts (\n\tid UUID NOT NULL, \n\tworkspace_id UUID NOT NULL, \n\tcase_id UUID NOT NULL, \n\treply TEXT NOT NULL, \n\toutcome VARCHAR(30) NOT NULL, \n\tcitations JSONB NOT NULL, \n\tversion INTEGER NOT NULL, \n\thistory JSONB NOT NULL, \n\tapproved_by UUID, \n\tfeedback VARCHAR(1000), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE, \n\tCONSTRAINT support_drafts_pkey PRIMARY KEY (id), \n\tCONSTRAINT support_drafts_workspace_id_fkey FOREIGN KEY(workspace_id, case_id) REFERENCES support_cases (workspace_id, id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute("CREATE INDEX support_drafts_workspace_id_idx ON support_drafts (workspace_id)")


def downgrade():
    op.drop_table("support_drafts")
    op.drop_table("support_chunks")
    op.drop_table("support_memberships")
    op.drop_table("support_jobs")
    op.drop_table("support_invitations")
    op.drop_table("support_documents")
    op.drop_table("support_cases")
    op.drop_table("support_audit")
    op.drop_table("support_workspaces")
