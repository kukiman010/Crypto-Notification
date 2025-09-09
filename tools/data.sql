SET client_encoding = 'UTF8';


create table users(
    user_id                 BIGINT UNIQUE,
    user_name               TEXT,
    tariff                  INT,
    type                    TEXT,
    language_code           TEXT,
    currency_code           TEXT DEFAULT 'USD',
    favorit_coins           TEXT[] DEFAULT '{}',
    wait_action             TEXT DEFAULT '',
    last_balance_mes_id     BIGINT DEFAULT 0,
    count_post_balance_mes  INT DEFAULT 0,
    code_time               INT DEFAULT 3,
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

CREATE TABLE crypto_notifications (
    id                      SERIAL PRIMARY KEY,
    user_id                 BIGINT NOT NULL,
    crypto_symbol           VARCHAR(10) NOT NULL,
    target_price            NUMERIC(18, 8) NOT NULL,
    trigger_direction       VARCHAR(8) NOT NULL, -- 'above' или 'below'
    comment                 TEXT,
    created_at              TIMESTAMP DEFAULT NOW()
);



create table time_zone (
    code_time               INT UNIQUE,
    _isView                 BOOLEAN DEFAULT TRUE,
    def_lang_code           TEXT,                   --- неужен для более удобно определения временной зоны по языку интерфейса пользователя
    description             TEXT
);


CREATE TABLE  currencies (
    currency_name           TEXT UNIQUE,
    code                    TEXT UNIQUE,
    _isView                 BOOLEAN
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
    p_language_code text,
    p_time_zone int
) RETURNS void AS $$
DECLARE
    tariff_val int;
BEGIN
    -- Получаем тариф из справочника
    SELECT value::int INTO tariff_val FROM default_data WHERE key = 'tariff';

    -- Добавляем пользователя
    INSERT INTO users (user_id, user_name, tariff, type, language_code, code_time)
    VALUES (p_user_id, p_user_name, tariff_val, p_type, p_language_code, p_time_zone)
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
    SET favorit_coins = (
        SELECT ARRAY(
            SELECT DISTINCT unnest(
                COALESCE(favorit_coins, ARRAY[]::TEXT[]) || p_coin
            )
        )
    )
    WHERE user_id = p_user_id
      AND NOT (COALESCE(favorit_coins, ARRAY[]::TEXT[]) @> ARRAY[p_coin]);
END;
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION remove_favorit_coin(p_user_id BIGINT, p_coin TEXT)
RETURNS void AS $$
BEGIN
    UPDATE users
    SET favorit_coins = (
        SELECT ARRAY(
            SELECT unnest(COALESCE(favorit_coins, ARRAY[]::TEXT[]))
            EXCEPT
            SELECT p_coin
        )
    )
    WHERE user_id = p_user_id
      AND COALESCE(favorit_coins, ARRAY[]::TEXT[]) @> ARRAY[p_coin];
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



CREATE OR REPLACE FUNCTION increment_post_balance_mes(p_user_id BIGINT)
RETURNS void AS $$
BEGIN
    UPDATE users
    SET count_post_balance_mes = count_post_balance_mes + 1
    WHERE user_id = p_user_id;
END;
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION get_unique_favorit_coins(days INT DEFAULT 0)
RETURNS TEXT[] AS $$
DECLARE
    unique_coins TEXT[];
BEGIN
    IF days > 0 THEN
        SELECT ARRAY(
            SELECT DISTINCT unnest_coin
            FROM users, unnest(favorit_coins) AS unnest_coin
            WHERE favorit_coins IS NOT NULL
              AND last_login >= NOW() - INTERVAL '1 day' * days
            ORDER BY unnest_coin
        )
        INTO unique_coins;
    ELSE
        SELECT ARRAY(
            SELECT DISTINCT unnest_coin
            FROM users, unnest(favorit_coins) AS unnest_coin
            WHERE favorit_coins IS NOT NULL
            ORDER BY unnest_coin
        )
        INTO unique_coins;
    END IF;
    RETURN unique_coins;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION add_crypto_notification(
    p_user_id BIGINT,
    p_crypto_symbol VARCHAR,
    p_target_price NUMERIC,
    p_trigger_direction VARCHAR, 
    p_comment TEXT DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    -- Простая проверка на корректность значения trigger_direction
    IF LOWER(p_trigger_direction) NOT IN ('>', '<', '=') THEN
        RAISE EXCEPTION 'Некорректное значение trigger_direction. Используйте only ''>'', ''<'', ''=''.';
    END IF;

    INSERT INTO crypto_notifications(user_id, crypto_symbol, target_price, trigger_direction, comment)
    VALUES (p_user_id, UPPER(p_crypto_symbol), p_target_price, LOWER(p_trigger_direction), p_comment);
END;
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION delete_crypto_notification(p_id INT)
RETURNS VOID AS $$
BEGIN
    DELETE FROM crypto_notifications WHERE id = p_id;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION get_crypto_notifications_by_user(p_user_id BIGINT)
RETURNS SETOF crypto_notifications AS $$
BEGIN
    RETURN QUERY
    SELECT *
    FROM crypto_notifications
    WHERE user_id = p_user_id
    ORDER BY created_at DESC;
END;
$$ LANGUAGE plpgsql;









insert into default_data values ('tariff',                          '1');
insert into default_data values ('global_payment',                  'True');
insert into default_data values ('last_activity_autoupdate',        '5');
insert into default_data values ('support_chat',                    '@assistant_gpts_help');
insert into default_data values ('time_zone',                       '3');
insert into default_data values ('autoupdate_currency',             '4');


insert into languages values ('Chine',      'zh', True);
insert into languages values ('Espanol',    'es', True);
insert into languages values ('English',    'en', True);
insert into languages values ('Russian',    'ru', True);
insert into languages values ('France',     'fr', True);


insert into time_zone values (-12,  True,   'en',           'UTC -12 Baker Island');
insert into time_zone values (-11,  True,   'en,sm',        'UTC -11 American Samoa, Niue');
insert into time_zone values (-10,  True,   'en,fr,ty',     'UTC -10 Hawaii, Tahiti');
insert into time_zone values (-9,   True,   'en,fr',        'UTC -9 Alaska, Marquesas Islands');
insert into time_zone values (-8,   True,   'en,fr',        'UTC -8 Los Angeles, Vancouver');
insert into time_zone values (-7,   True,   'en',           'UTC -7 Denver, Phoenix');
insert into time_zone values (-6,   True,   'en,es',        'UTC -6 Chicago, Ciudad de México');
insert into time_zone values (-5,   True,   'en,es',        'UTC -5 New York, Bogotá');
insert into time_zone values (-4,   True,   'es,pt',        'UTC -4 Caracas, Santiago');
insert into time_zone values (-3,   True,   'es,pt',        'UTC -3 Buenos Aires, Rio de Janeiro');
insert into time_zone values (-2,   True,   'en',           'UTC -2 South Georgia and the South Sandwich Islands');
insert into time_zone values (-1,   True,   'pt,es',        'UTC -1 Açores, Cabo Verde');
insert into time_zone values (0,    True,   'en,pt',        'UTC 0 London, Lisboa');
insert into time_zone values (1,    True,   'de,fr,it,nl',  'UTC +1 Berlin, Paris');
insert into time_zone values (2,    True,   'el,uk,ru',     'UTC +2 Αθήνα, Київ');
insert into time_zone values (3,    True,   'ru,ar',        'UTC +3 Москва, الرياض‎');
insert into time_zone values (4,    True,   'ar,az',        'UTC +4 دبي, Bakı');
insert into time_zone values (5,    True,   'ru,ur',        'UTC +5 Екатеринбург, سلام آباد‎');
insert into time_zone values (6,    True,   'kk,ky,ru',     'UTC +6 Алматы, Бишкек');
insert into time_zone values (7,    True,   'th,id,vi',     'UTC +7 กรุงเทพมหานคร, Jakarta');
insert into time_zone values (8,    True,   'zh,en',        'UTC +8 北京, Perth');
insert into time_zone values (9,    True,   'ja,ko',        'UTC +9 東京, 서울');
insert into time_zone values (10,   True,   'en,ru',        'UTC +10 Sydney, Владивосток');
insert into time_zone values (11,   True,   'en',           'UTC +11 Honiara, Port Vila');
insert into time_zone values (12,   True,   'en',           'UTC +12 Auckland, Suva');


insert into currencies values ('Dollar ($)','USD',          True);
insert into currencies values ('Euro (€)',  'EUR',          True);
insert into currencies values ('Рубль (₽)', 'RUB',          True);
insert into currencies values ('Yuán (¥)',  'CNY',          True);