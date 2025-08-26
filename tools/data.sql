SET client_encoding = 'UTF8';


create table users(
    user_id                 BIGINT UNIQUE,
    user_name               TEXT,
    tariff                  INT,
    type                    TEXT,
    language_code           TEXT,
    favorit_coins           TEXT[],
    wait_action             TEXT,
    last_balance_mes_id     BIGINT DEFAULT 0,
    count_post_balance_mes  INT DEFAULT 0,
    last_login              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
-- (
--     prem_id
--     usd
--     rub
--     stars
-- );




CREATE OR REPLACE FUNCTION add_user(
    p_user_id bigint,
    p_user_name text,
    p_type text,
    p_language_code text
) RETURNS void AS $$
DECLARE
    tariff_val int;
BEGIN
    -- Получаем тариф из справочника
    SELECT value::int INTO tariff_val FROM default_data WHERE key = 'tariff';

    -- Добавляем пользователя
    INSERT INTO users (user_id, user_name, tariff, type, language_code)
    VALUES (p_user_id, p_user_name, tariff_val, p_type, p_language_code)
    ON CONFLICT (user_id) DO NOTHING;  -- избежать дублей
END;
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION user_find(
    p_user_id BIGINT
)
RETURNS BOOLEAN AS $$
DECLARE
    v_exists BOOLEAN;
BEGIN
    -- Проверка на существование пользователя с заданным user_id
    SELECT EXISTS (SELECT 1 FROM users WHERE user_id = p_user_id) INTO v_exists;
    RETURN v_exists;
END;
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION update_wait_action(
    p_user_id bigint,
    p_wait_action text
) RETURNS void AS $$
BEGIN
    UPDATE users
    SET wait_action = p_wait_action
    WHERE user_id = p_user_id;
END;
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION update_last_login(
    p_user_id bigint
) RETURNS void AS $$
BEGIN
    UPDATE users
    SET last_login = CURRENT_TIMESTAMP
    WHERE user_id = p_user_id;
END;
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION update_last_balance_mes_id(
    p_user_id bigint,
    p_mes_id bigint
) RETURNS void AS $$
BEGIN
    UPDATE users
    SET last_balance_mes_id = p_mes_id
    WHERE user_id = p_user_id;
END;
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION update_count_post_balance_mes(
    p_user_id bigint,
    p_count int
) RETURNS void AS $$
BEGIN
    UPDATE users
    SET count_post_balance_mes = p_count
    WHERE user_id = p_user_id;
END;
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION add_favorit_coin(p_user_id BIGINT, p_coin TEXT)
RETURNS void AS $$
BEGIN
    UPDATE users
    SET favorit_coins = 
        ARRAY(
            SELECT DISTINCT unnest(favorit_coins || p_coin)
        )
    WHERE user_id = p_user_id 
      AND NOT favorit_coins @> ARRAY[p_coin];
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION remove_favorit_coin(p_user_id BIGINT, p_coin TEXT)
RETURNS void AS $$
BEGIN
    UPDATE users
    SET favorit_coins = ARRAY(
            SELECT unnest(favorit_coins)
            EXCEPT
            SELECT p_coin
        )
    WHERE user_id = p_user_id 
      AND favorit_coins @> ARRAY[p_coin];
END;
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION get_active_user_ids()
RETURNS SETOF BIGINT AS
$$
DECLARE
    recent_days INTEGER := 10; -- Значение по умолчанию
BEGIN
    -- Пробуем получить значение из default_data
    SELECT value::integer INTO recent_days
    FROM default_data
    WHERE key = 'last_activity_autoupdate'
    LIMIT 1;

    -- Если не найдено — recent_days останется 10

    RETURN QUERY
    SELECT user_id FROM users
    WHERE last_login >= NOW() - INTERVAL '1 day' * recent_days;
END;
$$
LANGUAGE plpgsql;




insert into default_data values ('tariff',                          '1');
insert into default_data values ('global_payment',                  'True');
insert into default_data values ('last_activity_autoupdate',        '5');
insert into default_data values ('support_chat',                    '@assistant_gpts_help');
insert into default_data values ('time_zone',                       'UTC');


insert into languages values ('Chine',      'zh', True);
insert into languages values ('Espanol',    'es', True);
insert into languages values ('English',    'en', True);
insert into languages values ('Russian',    'ru', True);
insert into languages values ('France',     'fr', True);