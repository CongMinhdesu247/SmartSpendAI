-- Schema from deployed commit 684c081, before private accounts.
CREATE TABLE plans (
	id SERIAL NOT NULL,
	title VARCHAR(255) NOT NULL,
	plan_type VARCHAR(50) NOT NULL,
	total_budget INTEGER NOT NULL,
	estimated_cost INTEGER NOT NULL,
	actual_spent INTEGER NOT NULL,
	region VARCHAR(120) NOT NULL,
	advice TEXT,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_plans_title ON plans (title);

CREATE INDEX ix_plans_id ON plans (id);

CREATE INDEX ix_plans_plan_type ON plans (plan_type);

CREATE TABLE spend_categories (
	id BIGSERIAL NOT NULL,
	name VARCHAR(80) NOT NULL,
	color VARCHAR(20) NOT NULL,
	archived BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (name)
);

ALTER TABLE spend_categories ENABLE ROW LEVEL SECURITY;

CREATE TABLE spend_goals (
	id BIGSERIAL NOT NULL,
	name VARCHAR(160) NOT NULL,
	target BIGINT NOT NULL,
	deadline DATE,
	archived BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	CHECK (target > 0 AND target <= 9000000000000)
);

ALTER TABLE spend_goals ENABLE ROW LEVEL SECURITY;

CREATE TABLE spend_preferences (
	key VARCHAR(50) NOT NULL,
	value TEXT NOT NULL,
	PRIMARY KEY (key)
);

ALTER TABLE spend_preferences ENABLE ROW LEVEL SECURITY;

CREATE TABLE spend_access_sessions (
	id VARCHAR(64) NOT NULL,
	password_version VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_spend_access_sessions_expires_at ON spend_access_sessions (expires_at);

ALTER TABLE spend_access_sessions ENABLE ROW LEVEL SECURITY;

CREATE TABLE plan_items (
	id SERIAL NOT NULL,
	plan_id INTEGER NOT NULL,
	category VARCHAR(50) NOT NULL,
	time_or_day VARCHAR(120) NOT NULL,
	name VARCHAR(255) NOT NULL,
	details TEXT,
	price INTEGER NOT NULL,
	is_completed BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(plan_id) REFERENCES plans (id) ON DELETE CASCADE
);

CREATE INDEX ix_plan_items_id ON plan_items (id);

CREATE INDEX ix_plan_items_category ON plan_items (category);

CREATE INDEX ix_plan_items_plan_id ON plan_items (plan_id);

CREATE TABLE spend_recurring (
	id BIGSERIAL NOT NULL,
	name VARCHAR(160) NOT NULL,
	amount BIGINT NOT NULL,
	category_id BIGINT NOT NULL,
	next_due DATE NOT NULL,
	frequency VARCHAR(12) NOT NULL,
	anchor_day INTEGER NOT NULL,
	archived BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	CHECK (amount > 0 AND amount <= 9000000000000),
	CHECK (frequency IN ('weekly','monthly','yearly')),
	CHECK (anchor_day BETWEEN 1 AND 31),
	FOREIGN KEY(category_id) REFERENCES spend_categories (id)
);

CREATE INDEX ix_spend_recurring_category_id ON spend_recurring (category_id);

CREATE INDEX ix_spend_recurring_next_due ON spend_recurring (next_due);

ALTER TABLE spend_recurring ENABLE ROW LEVEL SECURITY;

CREATE TABLE spend_budgets (
	key VARCHAR(60) NOT NULL,
	month DATE NOT NULL,
	category_id BIGINT,
	amount BIGINT NOT NULL,
	PRIMARY KEY (key),
	CHECK (amount >= 0 AND amount <= 9000000000000),
	FOREIGN KEY(category_id) REFERENCES spend_categories (id)
);

CREATE INDEX ix_spend_budgets_category_id ON spend_budgets (category_id);

CREATE INDEX ix_spend_budgets_month ON spend_budgets (month);

ALTER TABLE spend_budgets ENABLE ROW LEVEL SECURITY;

CREATE TABLE spend_contributions (
	id BIGSERIAL NOT NULL,
	client_id VARCHAR(80) NOT NULL,
	goal_id BIGINT NOT NULL,
	amount BIGINT NOT NULL,
	saved_on DATE NOT NULL,
	PRIMARY KEY (id),
	CHECK (amount > 0 AND amount <= 9000000000000),
	UNIQUE (client_id),
	FOREIGN KEY(goal_id) REFERENCES spend_goals (id)
);

CREATE INDEX ix_spend_contributions_goal_id ON spend_contributions (goal_id);

ALTER TABLE spend_contributions ENABLE ROW LEVEL SECURITY;

CREATE TABLE spend_plan_archive (
	id BIGSERIAL NOT NULL,
	snapshot TEXT NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE NOT NULL,
	restored BOOLEAN NOT NULL,
	restored_plan_id INTEGER,
	PRIMARY KEY (id),
	FOREIGN KEY(restored_plan_id) REFERENCES plans (id) ON DELETE SET NULL
);

CREATE INDEX ix_spend_plan_archive_restored_plan_id ON spend_plan_archive (restored_plan_id);

ALTER TABLE spend_plan_archive ENABLE ROW LEVEL SECURITY;

CREATE TABLE spend_transactions (
	id BIGSERIAL NOT NULL,
	client_id VARCHAR(80) NOT NULL,
	title VARCHAR(255) NOT NULL,
	search_title TEXT NOT NULL,
	amount BIGINT NOT NULL,
	kind VARCHAR(10) NOT NULL,
	spent_on DATE NOT NULL,
	category_id BIGINT NOT NULL,
	note TEXT NOT NULL,
	source_item_id INTEGER,
	recurring_id BIGINT,
	occurrence_on DATE,
	deleted_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (amount > 0 AND amount <= 9000000000000),
	CHECK (kind IN ('expense','income')),
	UNIQUE (recurring_id, occurrence_on),
	UNIQUE (client_id),
	FOREIGN KEY(category_id) REFERENCES spend_categories (id),
	UNIQUE (source_item_id),
	FOREIGN KEY(source_item_id) REFERENCES plan_items (id) ON DELETE SET NULL,
	FOREIGN KEY(recurring_id) REFERENCES spend_recurring (id)
);

CREATE INDEX ix_spend_transaction_month ON spend_transactions (spent_on, id);

CREATE INDEX ix_spend_transactions_recurring_id ON spend_transactions (recurring_id);

CREATE INDEX ix_spend_transactions_category_id ON spend_transactions (category_id);

ALTER TABLE spend_transactions ENABLE ROW LEVEL SECURITY;
