--
-- PostgreSQL database dump
--


-- Dumped from database version 18.1
-- Dumped by pg_dump version 18.1

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: order_side; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.order_side AS ENUM (
    'buy',
    'sell'
);


--
-- Name: order_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.order_status AS ENUM (
    'pending',
    'submitted',
    'partial_filled',
    'filled',
    'canceled',
    'failed'
);


--
-- Name: order_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.order_type AS ENUM (
    'limit',
    'market',
    'stop_limit',
    'stop_market',
    'ioc',
    'post_only'
);


--
-- Name: strategy_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.strategy_status AS ENUM (
    'stopped',
    'running',
    'paused',
    'error'
);


--
-- Name: strategy_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.strategy_type AS ENUM (
    'grid',
    'martin',
    'trend',
    'arbitrage',
    'custom',
    'swing_long',
    'ai_swing_long',
    'swing_short'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ai_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_configs (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(100) NOT NULL,
    provider character varying(50) DEFAULT 'deepseek'::character varying,
    api_key character varying(255) NOT NULL,
    model character varying(100) DEFAULT 'deepseek-chat'::character varying,
    is_active boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


--
-- Name: ai_configs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_configs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_configs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_configs_id_seq OWNED BY public.ai_configs.id;


--
-- Name: alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alerts (
    id integer NOT NULL,
    user_id integer NOT NULL,
    strategy_id integer,
    alert_type character varying(50) NOT NULL,
    severity character varying(20) DEFAULT 'info'::character varying NOT NULL,
    title character varying(200) NOT NULL,
    message text NOT NULL,
    data text,
    is_read boolean DEFAULT false,
    is_handled boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    handled_at timestamp with time zone
);


--
-- Name: alerts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.alerts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: alerts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.alerts_id_seq OWNED BY public.alerts.id;


--
-- Name: api_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_configs (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(100) NOT NULL,
    exchange character varying(50) DEFAULT 'OKX'::character varying NOT NULL,
    api_key character varying(255) NOT NULL,
    secret_key text NOT NULL,
    passphrase character varying(255) NOT NULL,
    is_simulated boolean DEFAULT false,
    is_active boolean DEFAULT false,
    proxy character varying(255),
    is_valid boolean DEFAULT true,
    last_verified_at timestamp with time zone,
    error_message text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: api_configs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.api_configs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: api_configs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.api_configs_id_seq OWNED BY public.api_configs.id;


--
-- Name: backtest_trades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_trades (
    id integer NOT NULL,
    backtest_id integer NOT NULL,
    "timestamp" bigint NOT NULL,
    side character varying(10) NOT NULL,
    price numeric(20,8) NOT NULL,
    amount numeric(20,8) NOT NULL,
    fee numeric(20,8) NOT NULL,
    position_before numeric(20,8),
    position_after numeric(20,8),
    capital_before numeric(20,2),
    capital_after numeric(20,2),
    pnl numeric(20,8),
    pnl_percent numeric(10,4)
);


--
-- Name: backtest_trades_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.backtest_trades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: backtest_trades_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.backtest_trades_id_seq OWNED BY public.backtest_trades.id;


--
-- Name: backtests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtests (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    strategy_type character varying(50) NOT NULL,
    symbol character varying(20) NOT NULL,
    "interval" character varying(10) NOT NULL,
    start_time bigint NOT NULL,
    end_time bigint NOT NULL,
    initial_capital numeric(20,2) DEFAULT 10000 NOT NULL,
    parameters jsonb,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    progress integer DEFAULT 0,
    error_message text,
    final_capital numeric(20,2),
    total_return numeric(10,4),
    annualized_return numeric(10,4),
    max_drawdown numeric(10,4),
    sharpe_ratio numeric(10,4),
    total_trades integer DEFAULT 0,
    winning_trades integer DEFAULT 0,
    losing_trades integer DEFAULT 0,
    win_rate numeric(10,4),
    profit_factor numeric(10,4),
    total_fee numeric(20,8),
    equity_curve jsonb,
    trade_history jsonb,
    position_history jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp without time zone
);


--
-- Name: backtests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.backtests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: backtests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.backtests_id_seq OWNED BY public.backtests.id;


--
-- Name: klines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.klines (
    id integer NOT NULL,
    symbol character varying(20) NOT NULL,
    "interval" character varying(10) NOT NULL,
    "timestamp" bigint NOT NULL,
    open numeric(20,8) NOT NULL,
    high numeric(20,8) NOT NULL,
    low numeric(20,8) NOT NULL,
    close numeric(20,8) NOT NULL,
    volume numeric(30,8) NOT NULL,
    volume_currency numeric(30,8) NOT NULL,
    confirm integer DEFAULT 1
);


--
-- Name: klines_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.klines_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: klines_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.klines_id_seq OWNED BY public.klines.id;


--
-- Name: orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orders (
    id integer NOT NULL,
    user_id integer NOT NULL,
    strategy_id integer,
    order_id character varying(100),
    symbol character varying(50) NOT NULL,
    side public.order_side NOT NULL,
    order_type public.order_type NOT NULL,
    status public.order_status DEFAULT 'pending'::public.order_status,
    price numeric,
    amount numeric NOT NULL,
    filled_amount numeric DEFAULT 0.0,
    avg_price numeric,
    fee numeric DEFAULT 0.0,
    fee_currency character varying(10),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    submitted_at timestamp with time zone,
    filled_at timestamp with time zone,
    canceled_at timestamp with time zone,
    note character varying(255)
);


--
-- Name: orders_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.orders_id_seq OWNED BY public.orders.id;


--
-- Name: positions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.positions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    strategy_id integer,
    symbol character varying(50) NOT NULL,
    amount numeric NOT NULL,
    available_amount numeric NOT NULL,
    frozen_amount numeric DEFAULT 0.0,
    avg_price numeric NOT NULL,
    total_cost numeric NOT NULL,
    unrealized_pnl numeric DEFAULT 0.0,
    realized_pnl numeric DEFAULT 0.0,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);


--
-- Name: positions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.positions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: positions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.positions_id_seq OWNED BY public.positions.id;


--
-- Name: risk_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_actions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    strategy_id integer,
    risk_control_id integer,
    action_type character varying(20) NOT NULL,
    trigger_reason text NOT NULL,
    risk_metrics text,
    execution_status character varying(20) DEFAULT 'success'::character varying NOT NULL,
    execution_details text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: risk_actions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.risk_actions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: risk_actions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.risk_actions_id_seq OWNED BY public.risk_actions.id;


--
-- Name: risk_controls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_controls (
    id integer NOT NULL,
    user_id integer NOT NULL,
    strategy_id integer,
    level character varying(20) DEFAULT 'strategy'::character varying NOT NULL,
    risk_type character varying(50) NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    is_enabled boolean DEFAULT true,
    min_available_balance double precision,
    max_position_value double precision,
    max_order_amount double precision,
    max_drawdown_percent double precision,
    daily_loss_limit double precision,
    total_loss_limit double precision,
    max_consecutive_losses integer,
    max_position_per_symbol double precision,
    max_concentration_ratio double precision,
    max_trades_per_period integer,
    period_seconds integer,
    action_on_trigger character varying(20) DEFAULT 'warn'::character varying NOT NULL,
    warning_threshold double precision DEFAULT 0.8,
    auto_resume boolean DEFAULT false,
    is_triggered boolean DEFAULT false,
    trigger_count integer DEFAULT 0,
    last_trigger_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: risk_controls_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.risk_controls_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: risk_controls_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.risk_controls_id_seq OWNED BY public.risk_controls.id;


--
-- Name: strategies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategies (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(100) NOT NULL,
    type public.strategy_type NOT NULL,
    status public.strategy_status DEFAULT 'stopped'::public.strategy_status,
    symbol character varying(50) NOT NULL,
    timeframe character varying(10),
    parameters jsonb,
    max_position numeric,
    stop_loss numeric,
    take_profit numeric,
    total_profit numeric DEFAULT 0.0,
    total_trades integer DEFAULT 0,
    win_rate numeric DEFAULT 0.0,
    description text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone,
    started_at timestamp with time zone,
    stopped_at timestamp with time zone
);


--
-- Name: strategies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.strategies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: strategies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.strategies_id_seq OWNED BY public.strategies.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(50) NOT NULL,
    email character varying(100),
    hashed_password character varying(255) NOT NULL,
    is_active boolean DEFAULT true,
    is_superuser boolean DEFAULT false,
    okx_api_key character varying(255),
    okx_secret_key character varying(255),
    okx_passphrase character varying(255),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: ai_configs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_configs ALTER COLUMN id SET DEFAULT nextval('public.ai_configs_id_seq'::regclass);


--
-- Name: alerts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts ALTER COLUMN id SET DEFAULT nextval('public.alerts_id_seq'::regclass);


--
-- Name: api_configs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_configs ALTER COLUMN id SET DEFAULT nextval('public.api_configs_id_seq'::regclass);


--
-- Name: backtest_trades id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_trades ALTER COLUMN id SET DEFAULT nextval('public.backtest_trades_id_seq'::regclass);


--
-- Name: backtests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtests ALTER COLUMN id SET DEFAULT nextval('public.backtests_id_seq'::regclass);


--
-- Name: klines id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.klines ALTER COLUMN id SET DEFAULT nextval('public.klines_id_seq'::regclass);


--
-- Name: orders id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders ALTER COLUMN id SET DEFAULT nextval('public.orders_id_seq'::regclass);


--
-- Name: positions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.positions ALTER COLUMN id SET DEFAULT nextval('public.positions_id_seq'::regclass);


--
-- Name: risk_actions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_actions ALTER COLUMN id SET DEFAULT nextval('public.risk_actions_id_seq'::regclass);


--
-- Name: risk_controls id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_controls ALTER COLUMN id SET DEFAULT nextval('public.risk_controls_id_seq'::regclass);


--
-- Name: strategies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategies ALTER COLUMN id SET DEFAULT nextval('public.strategies_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: ai_configs ai_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_configs
    ADD CONSTRAINT ai_configs_pkey PRIMARY KEY (id);


--
-- Name: alerts alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_pkey PRIMARY KEY (id);


--
-- Name: api_configs api_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_configs
    ADD CONSTRAINT api_configs_pkey PRIMARY KEY (id);


--
-- Name: backtest_trades backtest_trades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_trades
    ADD CONSTRAINT backtest_trades_pkey PRIMARY KEY (id);


--
-- Name: backtests backtests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtests
    ADD CONSTRAINT backtests_pkey PRIMARY KEY (id);


--
-- Name: klines klines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.klines
    ADD CONSTRAINT klines_pkey PRIMARY KEY (id);


--
-- Name: orders orders_order_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_order_id_key UNIQUE (order_id);


--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);


--
-- Name: positions positions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.positions
    ADD CONSTRAINT positions_pkey PRIMARY KEY (id);


--
-- Name: risk_actions risk_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_actions
    ADD CONSTRAINT risk_actions_pkey PRIMARY KEY (id);


--
-- Name: risk_controls risk_controls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_controls
    ADD CONSTRAINT risk_controls_pkey PRIMARY KEY (id);


--
-- Name: strategies strategies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategies
    ADD CONSTRAINT strategies_pkey PRIMARY KEY (id);


--
-- Name: klines uix_symbol_interval_timestamp; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.klines
    ADD CONSTRAINT uix_symbol_interval_timestamp UNIQUE (symbol, "interval", "timestamp");


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: idx_alerts_alert_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_alert_type ON public.alerts USING btree (alert_type);


--
-- Name: idx_alerts_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_created_at ON public.alerts USING btree (created_at DESC);


--
-- Name: idx_alerts_is_read; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_is_read ON public.alerts USING btree (is_read);


--
-- Name: idx_alerts_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_strategy_id ON public.alerts USING btree (strategy_id);


--
-- Name: idx_alerts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_user_id ON public.alerts USING btree (user_id);


--
-- Name: idx_api_configs_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_api_configs_is_active ON public.api_configs USING btree (is_active);


--
-- Name: idx_api_configs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_api_configs_user_id ON public.api_configs USING btree (user_id);


--
-- Name: idx_backtest_trades_backtest_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_backtest_trades_backtest_id ON public.backtest_trades USING btree (backtest_id);


--
-- Name: idx_backtest_trades_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_backtest_trades_timestamp ON public.backtest_trades USING btree ("timestamp");


--
-- Name: idx_backtests_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_backtests_created_at ON public.backtests USING btree (created_at);


--
-- Name: idx_backtests_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_backtests_status ON public.backtests USING btree (status);


--
-- Name: idx_backtests_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_backtests_user_id ON public.backtests USING btree (user_id);


--
-- Name: idx_klines_interval; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_klines_interval ON public.klines USING btree ("interval");


--
-- Name: idx_klines_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_klines_symbol ON public.klines USING btree (symbol);


--
-- Name: idx_klines_symbol_interval_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_klines_symbol_interval_timestamp ON public.klines USING btree (symbol, "interval", "timestamp");


--
-- Name: idx_klines_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_klines_timestamp ON public.klines USING btree ("timestamp");


--
-- Name: idx_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orders_status ON public.orders USING btree (status);


--
-- Name: idx_orders_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orders_strategy_id ON public.orders USING btree (strategy_id);


--
-- Name: idx_orders_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orders_symbol ON public.orders USING btree (symbol);


--
-- Name: idx_orders_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orders_user_id ON public.orders USING btree (user_id);


--
-- Name: idx_positions_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_positions_symbol ON public.positions USING btree (symbol);


--
-- Name: idx_positions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_positions_user_id ON public.positions USING btree (user_id);


--
-- Name: idx_risk_actions_action_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_actions_action_type ON public.risk_actions USING btree (action_type);


--
-- Name: idx_risk_actions_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_actions_created_at ON public.risk_actions USING btree (created_at DESC);


--
-- Name: idx_risk_actions_risk_control_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_actions_risk_control_id ON public.risk_actions USING btree (risk_control_id);


--
-- Name: idx_risk_actions_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_actions_strategy_id ON public.risk_actions USING btree (strategy_id);


--
-- Name: idx_risk_actions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_actions_user_id ON public.risk_actions USING btree (user_id);


--
-- Name: idx_risk_controls_is_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_controls_is_enabled ON public.risk_controls USING btree (is_enabled);


--
-- Name: idx_risk_controls_is_triggered; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_controls_is_triggered ON public.risk_controls USING btree (is_triggered);


--
-- Name: idx_risk_controls_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_controls_level ON public.risk_controls USING btree (level);


--
-- Name: idx_risk_controls_risk_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_controls_risk_type ON public.risk_controls USING btree (risk_type);


--
-- Name: idx_risk_controls_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_controls_strategy_id ON public.risk_controls USING btree (strategy_id);


--
-- Name: idx_risk_controls_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_risk_controls_user_id ON public.risk_controls USING btree (user_id);


--
-- Name: idx_strategies_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_strategies_status ON public.strategies USING btree (status);


--
-- Name: idx_strategies_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_strategies_user_id ON public.strategies USING btree (user_id);


--
-- Name: alerts alerts_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(id) ON DELETE CASCADE;


--
-- Name: alerts alerts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: api_configs api_configs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_configs
    ADD CONSTRAINT api_configs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: backtest_trades backtest_trades_backtest_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_trades
    ADD CONSTRAINT backtest_trades_backtest_id_fkey FOREIGN KEY (backtest_id) REFERENCES public.backtests(id) ON DELETE CASCADE;


--
-- Name: orders orders_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(id) ON DELETE SET NULL;


--
-- Name: orders orders_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: positions positions_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.positions
    ADD CONSTRAINT positions_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(id) ON DELETE SET NULL;


--
-- Name: positions positions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.positions
    ADD CONSTRAINT positions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: risk_actions risk_actions_risk_control_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_actions
    ADD CONSTRAINT risk_actions_risk_control_id_fkey FOREIGN KEY (risk_control_id) REFERENCES public.risk_controls(id) ON DELETE SET NULL;


--
-- Name: risk_actions risk_actions_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_actions
    ADD CONSTRAINT risk_actions_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(id) ON DELETE SET NULL;


--
-- Name: risk_actions risk_actions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_actions
    ADD CONSTRAINT risk_actions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: risk_controls risk_controls_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_controls
    ADD CONSTRAINT risk_controls_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(id) ON DELETE CASCADE;


--
-- Name: risk_controls risk_controls_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_controls
    ADD CONSTRAINT risk_controls_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: strategies strategies_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategies
    ADD CONSTRAINT strategies_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict rsRPDmw99SdFXBnegZdZ4J0pedF61P06VU2YziI5Mo1EcN0afp9egADqTHiiMCa

