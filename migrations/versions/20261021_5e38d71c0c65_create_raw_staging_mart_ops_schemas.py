"""create raw staging mart ops schemas

Revision ID: 5e38d71c0c65
Revises: 
Create Date: 2026-10-21 18:09:10.476907
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '5e38d71c0c65'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ops est créé par migrations/env.py (il contient la table alembic_version)
LAYER_SCHEMAS = ("raw", "staging", "mart")


def upgrade() -> None:
    for schema in LAYER_SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    op.create_table('model_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('model_type', sa.String(length=10), nullable=False),
    sa.Column('algorithm', sa.String(length=100), nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('artifact_path', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('trained_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("model_type IN ('pd', 'lgd', 'ead')", name=op.f('ck_model_runs_model_type')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_model_runs')),
    schema='mart'
    )
    op.create_index('uq_model_runs_active_per_type', 'model_runs', ['model_type'], unique=True, schema='mart', postgresql_where='is_active')
    op.create_table('etl_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('step', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='running', nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rows_in', sa.BigInteger(), nullable=True),
    sa.Column('rows_out', sa.BigInteger(), nullable=True),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.CheckConstraint("status IN ('running', 'success', 'failed')", name=op.f('ck_etl_runs_status')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_etl_runs')),
    schema='ops'
    )
    op.create_table('loans',
    sa.Column('loan_id', sa.BigInteger(), autoincrement=False, nullable=False),
    sa.Column('term', sa.String(length=20), nullable=True),
    sa.Column('int_rate', sa.Double(), nullable=True),
    sa.Column('installment', sa.Double(), nullable=True),
    sa.Column('grade', sa.String(length=5), nullable=True),
    sa.Column('emp_length', sa.String(length=20), nullable=True),
    sa.Column('home_ownership', sa.String(length=20), nullable=True),
    sa.Column('annual_inc', sa.Double(), nullable=True),
    sa.Column('loan_status', sa.String(length=50), nullable=True),
    sa.Column('dti', sa.Double(), nullable=True),
    sa.Column('tot_cur_bal', sa.Double(), nullable=True),
    sa.Column('open_acc_6m', sa.Double(), nullable=True),
    sa.Column('total_bal_il', sa.Double(), nullable=True),
    sa.Column('inq_fi', sa.Double(), nullable=True),
    sa.Column('mort_acc', sa.Double(), nullable=True),
    sa.Column('num_sats', sa.Double(), nullable=True),
    sa.Column('out_prncp', sa.Double(), nullable=True),
    sa.Column('total_pymnt', sa.Double(), nullable=True),
    sa.Column('recoveries', sa.Double(), nullable=True),
    sa.Column('etl_run_id', sa.Integer(), nullable=False),
    sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['etl_run_id'], ['ops.etl_runs.id'], name=op.f('fk_loans_etl_run_id_etl_runs')),
    sa.PrimaryKeyConstraint('loan_id', name=op.f('pk_loans')),
    schema='raw'
    )
    op.create_table('loans',
    sa.Column('loan_id', sa.BigInteger(), nullable=False),
    sa.Column('dataset', sa.String(length=10), nullable=False),
    sa.Column('term', sa.String(length=20), nullable=False),
    sa.Column('int_rate', sa.Double(), nullable=False),
    sa.Column('installment', sa.Double(), nullable=False),
    sa.Column('grade', sa.String(length=5), nullable=False),
    sa.Column('emp_length', sa.String(length=20), nullable=False),
    sa.Column('home_ownership', sa.String(length=20), nullable=False),
    sa.Column('annual_inc', sa.Double(), nullable=False),
    sa.Column('loan_status', sa.String(length=50), nullable=False),
    sa.Column('dti', sa.Double(), nullable=False),
    sa.Column('tot_cur_bal', sa.Double(), nullable=False),
    sa.Column('open_acc_6m', sa.Double(), nullable=False),
    sa.Column('total_bal_il', sa.Double(), nullable=False),
    sa.Column('inq_fi', sa.Double(), nullable=False),
    sa.Column('mort_acc', sa.Double(), nullable=False),
    sa.Column('num_sats', sa.Double(), nullable=False),
    sa.Column('out_prncp', sa.Double(), nullable=True),
    sa.Column('total_pymnt', sa.Double(), nullable=True),
    sa.Column('recoveries', sa.Double(), nullable=True),
    sa.Column('etl_run_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("dataset IN ('train', 'test')", name=op.f('ck_loans_dataset')),
    sa.CheckConstraint("grade IN ('A', 'B', 'C', 'D', 'E', 'F', 'G')", name=op.f('ck_loans_grade')),
    sa.CheckConstraint("loan_status IN ('Fully Paid', 'Charged Off')", name=op.f('ck_loans_loan_status')),
    sa.CheckConstraint("term IN (' 36 months', ' 60 months')", name=op.f('ck_loans_term')),
    sa.CheckConstraint('int_rate >= 0 AND annual_inc >= 0', name=op.f('ck_loans_positive_amounts')),
    sa.ForeignKeyConstraint(['etl_run_id'], ['ops.etl_runs.id'], name=op.f('fk_loans_etl_run_id_etl_runs')),
    sa.ForeignKeyConstraint(['loan_id'], ['raw.loans.loan_id'], name=op.f('fk_loans_loan_id_loans')),
    sa.PrimaryKeyConstraint('loan_id', name=op.f('pk_loans')),
    schema='staging'
    )
    op.create_index('ix_staging_loans_dataset', 'loans', ['dataset'], unique=False, schema='staging')
    op.create_table('ecl_results',
    sa.Column('loan_id', sa.BigInteger(), nullable=False),
    sa.Column('model_run_id', sa.Integer(), nullable=False),
    sa.Column('stage', sa.Integer(), server_default='1', nullable=False),
    sa.Column('pd', sa.Double(), nullable=False),
    sa.Column('lgd', sa.Double(), nullable=False),
    sa.Column('ead', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('ecl', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('ead >= 0 AND ecl >= 0', name=op.f('ck_ecl_results_positive_amounts')),
    sa.CheckConstraint('lgd BETWEEN 0 AND 1', name=op.f('ck_ecl_results_lgd_range')),
    sa.CheckConstraint('pd BETWEEN 0 AND 1', name=op.f('ck_ecl_results_pd_range')),
    sa.CheckConstraint('stage IN (1, 2, 3)', name=op.f('ck_ecl_results_stage')),
    sa.ForeignKeyConstraint(['loan_id'], ['staging.loans.loan_id'], name=op.f('fk_ecl_results_loan_id_loans')),
    sa.ForeignKeyConstraint(['model_run_id'], ['mart.model_runs.id'], name=op.f('fk_ecl_results_model_run_id_model_runs')),
    sa.PrimaryKeyConstraint('loan_id', 'model_run_id', name=op.f('pk_ecl_results')),
    schema='mart'
    )
    op.create_table('pd_scores',
    sa.Column('loan_id', sa.BigInteger(), nullable=False),
    sa.Column('model_run_id', sa.Integer(), nullable=False),
    sa.Column('pd', sa.Double(), nullable=False),
    sa.Column('scored_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('pd BETWEEN 0 AND 1', name=op.f('ck_pd_scores_pd_range')),
    sa.ForeignKeyConstraint(['loan_id'], ['staging.loans.loan_id'], name=op.f('fk_pd_scores_loan_id_loans')),
    sa.ForeignKeyConstraint(['model_run_id'], ['mart.model_runs.id'], name=op.f('fk_pd_scores_model_run_id_model_runs')),
    sa.PrimaryKeyConstraint('loan_id', 'model_run_id', name=op.f('pk_pd_scores')),
    schema='mart'
    )


def downgrade() -> None:
    op.drop_table('pd_scores', schema='mart')
    op.drop_table('ecl_results', schema='mart')
    op.drop_index('ix_staging_loans_dataset', table_name='loans', schema='staging')
    op.drop_table('loans', schema='staging')
    op.drop_table('loans', schema='raw')
    op.drop_table('etl_runs', schema='ops')
    op.drop_index('uq_model_runs_active_per_type', table_name='model_runs', schema='mart', postgresql_where='is_active')
    op.drop_table('model_runs', schema='mart')

    for schema in reversed(LAYER_SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema}")
