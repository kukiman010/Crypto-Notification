SET client_encoding = 'UTF8';


create table users(
    user_id                 BIGINT UNIQUE,
    user_name               TEXT,
    tariff                  INT DEFAULT 1,
    favorit_coins           TEXT[],
    status                  TEXT,
    last_balance_mes_id     BIGINT DEFAULT 0,
    count_post_balance_mes  INT DEFAULT 0,
    last_login              TIMESTAMP,
    registration            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    id                      BIGSERIAL PRIMARY KEY
);

CREATE TABLE default_data (
    key                     TEXT UNIQUE,
    value                   TEXT
);

CREATE TABLE languages (
    language                TEXT UNIQUE,
    code                    TEXT,
    _isView                 BOOLEAN
);

create table users_notification
(
    user_id                 BIGINT UNIQUE,
    json                    jsonb,                  --- json( coin_code: {price, description}
    id                      BIGSERIAL PRIMARY KEY
);

-- create table premium
-- {
--     prem_id
--     usd
--     rub
--     stars
-- };

