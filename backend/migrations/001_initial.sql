--
-- PostgreSQL database dump
--

\restrict BfWF97FxO8IFeK2VMnDkWNNbwX7BSN5jpdaShZxAsSbwa9c83qecCpECYHRE4Dg

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: audits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audits (
    id integer NOT NULL,
    actor character varying(100),
    action character varying(200),
    created character varying(40)
);


--
-- Name: audits_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audits_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audits_id_seq OWNED BY public.audits.id;


--
-- Name: outreaches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.outreaches (
    id integer NOT NULL,
    segment_id integer,
    cluster_id integer,
    title character varying(100),
    note text,
    members json,
    status character varying(20)
);


--
-- Name: outreaches_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.outreaches_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: outreaches_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.outreaches_id_seq OWNED BY public.outreaches.id;


--
-- Name: readers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.readers (
    id integer NOT NULL,
    code character varying(60) NOT NULL,
    weekly_reading double precision,
    completion double precision,
    night_share double precision,
    note text
);


--
-- Name: readers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.readers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: readers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.readers_id_seq OWNED BY public.readers.id;


--
-- Name: segments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.segments (
    id integer NOT NULL,
    name character varying(100),
    k integer,
    features json,
    state character varying(20),
    result json,
    error text
);


--
-- Name: segments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.segments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: segments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.segments_id_seq OWNED BY public.segments.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    email character varying(100),
    password character varying(200),
    role character varying(20)
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
-- Name: audits id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audits ALTER COLUMN id SET DEFAULT nextval('public.audits_id_seq'::regclass);


--
-- Name: outreaches id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.outreaches ALTER COLUMN id SET DEFAULT nextval('public.outreaches_id_seq'::regclass);


--
-- Name: readers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.readers ALTER COLUMN id SET DEFAULT nextval('public.readers_id_seq'::regclass);


--
-- Name: segments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.segments ALTER COLUMN id SET DEFAULT nextval('public.segments_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: audits audits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audits
    ADD CONSTRAINT audits_pkey PRIMARY KEY (id);


--
-- Name: outreaches outreaches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.outreaches
    ADD CONSTRAINT outreaches_pkey PRIMARY KEY (id);


--
-- Name: readers readers_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.readers
    ADD CONSTRAINT readers_code_key UNIQUE (code);


--
-- Name: readers readers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.readers
    ADD CONSTRAINT readers_pkey PRIMARY KEY (id);


--
-- Name: segments segments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.segments
    ADD CONSTRAINT segments_pkey PRIMARY KEY (id);


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
-- Name: outreaches outreaches_segment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.outreaches
    ADD CONSTRAINT outreaches_segment_id_fkey FOREIGN KEY (segment_id) REFERENCES public.segments(id);


--
-- PostgreSQL database dump complete
--

\unrestrict BfWF97FxO8IFeK2VMnDkWNNbwX7BSN5jpdaShZxAsSbwa9c83qecCpECYHRE4Dg


--
-- 订阅权益、修订与批次（solo-2611）
-- 说明：本次同样以 ORM 建初表；以下保留与实体一致的 DDL，便于审计与手工重建。
--

CREATE TABLE public.subscription_batches (
    id integer NOT NULL,
    name character varying(120),
    import_key character varying(120),
    state character varying(20),
    submitted_by character varying(100),
    created character varying(40),
    verified_by character varying(100),
    verified_at character varying(40),
    total_rows integer,
    accepted_rows integer,
    duplicate_rows integer,
    rejected_rows integer,
    superseded_rows integer,
    problem_rows integer,
    rejected json,
    entitlement_version integer,
    version_checksum character varying(64)
);

CREATE SEQUENCE public.subscription_batches_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.subscription_batches_id_seq OWNED BY public.subscription_batches.id;
ALTER TABLE ONLY public.subscription_batches ALTER COLUMN id SET DEFAULT nextval('public.subscription_batches_id_seq'::regclass);
ALTER TABLE ONLY public.subscription_batches ADD CONSTRAINT subscription_batches_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.subscription_batches ADD CONSTRAINT subscription_batches_import_key_key UNIQUE (import_key);

CREATE TABLE public.subscription_events (
    id integer NOT NULL,
    batch_id integer NOT NULL,
    line_no integer NOT NULL,
    order_no character varying(80) NOT NULL,
    member_code character varying(60) NOT NULL,
    revision integer NOT NULL,
    effective_start date NOT NULL,
    effective_end date NOT NULL,
    refunded_on date,
    raw json
);

CREATE SEQUENCE public.subscription_events_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.subscription_events_id_seq OWNED BY public.subscription_events.id;
ALTER TABLE ONLY public.subscription_events ALTER COLUMN id SET DEFAULT nextval('public.subscription_events_id_seq'::regclass);
ALTER TABLE ONLY public.subscription_events ADD CONSTRAINT subscription_events_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.subscription_events ADD CONSTRAINT uq_event_order_revision UNIQUE (order_no, revision);
ALTER TABLE ONLY public.subscription_events ADD CONSTRAINT uq_event_batch_line UNIQUE (batch_id, line_no);
CREATE INDEX ix_subscription_events_member ON public.subscription_events (member_code);
CREATE INDEX ix_subscription_events_batch ON public.subscription_events (batch_id);
ALTER TABLE ONLY public.subscription_events ADD CONSTRAINT subscription_events_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.subscription_batches(id);

CREATE TABLE public.entitlement_versions (
    id integer NOT NULL,
    version integer NOT NULL,
    batch_id integer,
    created character varying(40),
    checksum character varying(64),
    members integer,
    ranges integer
);

CREATE SEQUENCE public.entitlement_versions_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.entitlement_versions_id_seq OWNED BY public.entitlement_versions.id;
ALTER TABLE ONLY public.entitlement_versions ALTER COLUMN id SET DEFAULT nextval('public.entitlement_versions_id_seq'::regclass);
ALTER TABLE ONLY public.entitlement_versions ADD CONSTRAINT entitlement_versions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.entitlement_versions ADD CONSTRAINT entitlement_versions_version_key UNIQUE (version);
ALTER TABLE ONLY public.entitlement_versions ADD CONSTRAINT entitlement_versions_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.subscription_batches(id);

CREATE TABLE public.entitlement_snapshots (
    id integer NOT NULL,
    version integer NOT NULL,
    member_code character varying(60) NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    days integer NOT NULL,
    source_orders json
);

CREATE SEQUENCE public.entitlement_snapshots_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.entitlement_snapshots_id_seq OWNED BY public.entitlement_snapshots.id;
ALTER TABLE ONLY public.entitlement_snapshots ALTER COLUMN id SET DEFAULT nextval('public.entitlement_snapshots_id_seq'::regclass);
ALTER TABLE ONLY public.entitlement_snapshots ADD CONSTRAINT entitlement_snapshots_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.entitlement_snapshots ADD CONSTRAINT uq_snapshot_version_member_start UNIQUE (version, member_code, start_date);
CREATE INDEX ix_entitlement_snapshots_version ON public.entitlement_snapshots (version);
CREATE INDEX ix_snapshot_member_range ON public.entitlement_snapshots (member_code, start_date, end_date);

ALTER TABLE public.segments ADD COLUMN week_start date;
ALTER TABLE public.segments ADD COLUMN week_end date;
ALTER TABLE public.segments ADD COLUMN entitlement_version integer;
ALTER TABLE public.segments ADD COLUMN qualification json;

ALTER TABLE public.outreaches ADD COLUMN send_date date;
ALTER TABLE public.outreaches ADD COLUMN entitlement_version integer;
ALTER TABLE public.outreaches ADD COLUMN entitlement_basis json;
ALTER TABLE public.outreaches ADD COLUMN approved_by character varying(100);
ALTER TABLE public.outreaches ADD COLUMN approved_at character varying(40);
