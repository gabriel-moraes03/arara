-- análise refeita para a mesma área: a antiga fica no banco e no disco (acessível pelo id), fora dos cards
alter table analysis add column superseded_by varchar(64);
