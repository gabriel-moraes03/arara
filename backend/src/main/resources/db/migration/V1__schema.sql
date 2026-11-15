-- tipos portáveis: text e double precision valem no PostgreSQL e no H2 (testes, modo PostgreSQL)
create table analysis (
  id                varchar(64) primary key,
  hash              varchar(64) not null,
  name              varchar(200),
  status            varchar(20) not null,
  aoi_geojson       text not null,
  west double precision not null, south double precision not null,
  east double precision not null, north double precision not null,
  area_km2          double precision not null,
  start_date        varchar(10),
  end_date          varchar(10),
  group_id          varchar(200),
  maturity          varchar(20),
  algorithm_version varchar(60) not null,
  reason            text,
  experimental      boolean,
  summary_json      text,
  created_at        timestamp not null,
  updated_at        timestamp not null,
  completed_at      timestamp
);
create index analysis_status on analysis (status);

create table job (
  id          varchar(36) primary key,
  analysis_id varchar(64) not null,
  status      varchar(20) not null,
  stage       varchar(40),
  progress    double precision not null default 0,
  message     text,
  reason      text,
  created_at  timestamp not null,
  updated_at  timestamp not null
);
create index job_status on job (status);
create index job_analysis on job (analysis_id);
