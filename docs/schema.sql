-- Generated with pg_dump from the database built by the Alembic migrations
-- (backend/alembic/versions/). See schema.md for the reasoning.

CREATE TYPE public.auction_event_type AS ENUM (
    'AUCTION_CREATED',
    'BID_SUBMITTED',
    'EXTENDED',
    'EXTENSION_SKIPPED',
    'AUCTION_CLOSED',
    'AUCTION_FORCE_CLOSED'
);

CREATE TYPE public.trigger_type AS ENUM (
    'BID_RECEIVED',
    'ANY_RANK_CHANGE',
    'L1_CHANGE'
);

CREATE TYPE public.user_role AS ENUM (
    'BUYER',
    'SUPPLIER'
);

CREATE TABLE public.auction_events (
    id bigint NOT NULL,
    rfq_id integer NOT NULL,
    event_type public.auction_event_type NOT NULL,
    bid_id bigint,
    actor_id integer,
    previous_close_at timestamp with time zone,
    new_close_at timestamp with time zone,
    message text NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.auction_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.auction_events_id_seq OWNED BY public.auction_events.id;

CREATE TABLE public.bids (
    id bigint NOT NULL,
    rfq_id integer NOT NULL,
    supplier_id integer NOT NULL,
    carrier_name character varying(120) NOT NULL,
    freight_charges numeric(12,2) NOT NULL,
    origin_charges numeric(12,2) NOT NULL,
    destination_charges numeric(12,2) NOT NULL,
    total_amount numeric(14,2) GENERATED ALWAYS AS (((freight_charges + origin_charges) + destination_charges)) STORED NOT NULL,
    transit_time_days integer NOT NULL,
    quote_valid_until date NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_bids_destination_non_negative CHECK ((destination_charges >= (0)::numeric)),
    CONSTRAINT ck_bids_freight_non_negative CHECK ((freight_charges >= (0)::numeric)),
    CONSTRAINT ck_bids_origin_non_negative CHECK ((origin_charges >= (0)::numeric)),
    CONSTRAINT ck_bids_transit_time_positive CHECK ((transit_time_days > 0))
);

CREATE SEQUENCE public.bids_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.bids_id_seq OWNED BY public.bids.id;

CREATE SEQUENCE public.rfq_reference_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE public.rfqs (
    id integer NOT NULL,
    reference_id character varying(20) DEFAULT ('RFQ-'::text || lpad((nextval('public.rfq_reference_seq'::regclass))::text, 5, '0'::text)) NOT NULL,
    name character varying(200) NOT NULL,
    buyer_id integer NOT NULL,
    pickup_date date NOT NULL,
    bid_start_at timestamp with time zone NOT NULL,
    bid_close_at timestamp with time zone NOT NULL,
    current_close_at timestamp with time zone NOT NULL,
    forced_close_at timestamp with time zone,
    trigger_window_minutes integer,
    extension_minutes integer,
    trigger_type public.trigger_type,
    extension_count integer DEFAULT 0 NOT NULL,
    finalized_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    british_auction boolean DEFAULT true NOT NULL,
    CONSTRAINT ck_rfqs_bid_close_after_start CHECK ((bid_start_at < bid_close_at)),
    CONSTRAINT ck_rfqs_british_auction_settings CHECK (((british_auction AND (forced_close_at IS NOT NULL) AND (trigger_window_minutes IS NOT NULL) AND (extension_minutes IS NOT NULL) AND (trigger_type IS NOT NULL)) OR ((NOT british_auction) AND (forced_close_at IS NULL) AND (trigger_window_minutes IS NULL) AND (extension_minutes IS NULL) AND (trigger_type IS NULL)))),
    CONSTRAINT ck_rfqs_current_close_within_bounds CHECK (((current_close_at >= bid_close_at) AND (current_close_at <= COALESCE(forced_close_at, bid_close_at)))),
    CONSTRAINT ck_rfqs_extension_positive CHECK ((extension_minutes > 0)),
    CONSTRAINT ck_rfqs_forced_close_after_bid_close CHECK ((bid_close_at < forced_close_at)),
    CONSTRAINT ck_rfqs_trigger_window_positive CHECK ((trigger_window_minutes > 0))
);

CREATE SEQUENCE public.rfqs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.rfqs_id_seq OWNED BY public.rfqs.id;

CREATE TABLE public.users (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    company character varying(120) NOT NULL,
    role public.user_role NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;

ALTER TABLE ONLY public.auction_events ALTER COLUMN id SET DEFAULT nextval('public.auction_events_id_seq'::regclass);

ALTER TABLE ONLY public.bids ALTER COLUMN id SET DEFAULT nextval('public.bids_id_seq'::regclass);

ALTER TABLE ONLY public.rfqs ALTER COLUMN id SET DEFAULT nextval('public.rfqs_id_seq'::regclass);

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);

ALTER TABLE ONLY public.auction_events
    ADD CONSTRAINT pk_auction_events PRIMARY KEY (id);

ALTER TABLE ONLY public.bids
    ADD CONSTRAINT pk_bids PRIMARY KEY (id);

ALTER TABLE ONLY public.rfqs
    ADD CONSTRAINT pk_rfqs PRIMARY KEY (id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT pk_users PRIMARY KEY (id);

ALTER TABLE ONLY public.rfqs
    ADD CONSTRAINT uq_rfqs_reference_id UNIQUE (reference_id);

CREATE INDEX ix_auction_events_rfq_time ON public.auction_events USING btree (rfq_id, created_at, id);

CREATE INDEX ix_bids_rfq_supplier_latest ON public.bids USING btree (rfq_id, supplier_id, created_at DESC);

CREATE INDEX ix_bids_rfq_total ON public.bids USING btree (rfq_id, total_amount);

CREATE INDEX ix_rfqs_unfinalized_close ON public.rfqs USING btree (current_close_at) WHERE (finalized_at IS NULL);

ALTER TABLE ONLY public.auction_events
    ADD CONSTRAINT fk_auction_events_actor_id_users FOREIGN KEY (actor_id) REFERENCES public.users(id);

ALTER TABLE ONLY public.auction_events
    ADD CONSTRAINT fk_auction_events_bid_id_bids FOREIGN KEY (bid_id) REFERENCES public.bids(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.auction_events
    ADD CONSTRAINT fk_auction_events_rfq_id_rfqs FOREIGN KEY (rfq_id) REFERENCES public.rfqs(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.bids
    ADD CONSTRAINT fk_bids_rfq_id_rfqs FOREIGN KEY (rfq_id) REFERENCES public.rfqs(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.bids
    ADD CONSTRAINT fk_bids_supplier_id_users FOREIGN KEY (supplier_id) REFERENCES public.users(id);

ALTER TABLE ONLY public.rfqs
    ADD CONSTRAINT fk_rfqs_buyer_id_users FOREIGN KEY (buyer_id) REFERENCES public.users(id);
