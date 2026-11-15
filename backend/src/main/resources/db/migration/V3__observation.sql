-- Uma linha por passagem do radar em cada análise concluída. Fica mesmo quando os arquivos da análise
-- expiram (limpeza de 7 dias) e quando a análise é superada: é o histórico de cada região. Os números de
-- uma passagem dependem da série em que foram calculados (limiar único, referência = passagem mais seca),
-- por isso cada linha leva a análise e a versão do algoritmo de origem.
create table observation (
  analysis_id            varchar(64) not null,
  pass_date              varchar(10) not null,
  name                   varchar(200),
  west double precision not null, south double precision not null,
  east double precision not null, north double precision not null,
  granule                varchar(200),
  crid                   varchar(20),
  algorithm_version      varchar(60) not null,
  quality                varchar(30),
  water_km2              double precision,
  water_pct              double precision,
  flood_km2              double precision,
  flooded_vegetation_km2 double precision,
  reference_date         varchar(10),
  rain_3d_mm             double precision,
  rain_7d_mm             double precision,
  wind                   boolean,
  valid_fraction         double precision,
  threshold_db           double precision,
  confidence             varchar(10),
  confidence_reasons     text,
  computed_at            timestamp not null,
  primary key (analysis_id, pass_date)
);
create index observation_name_date on observation (name, pass_date);
