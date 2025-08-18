


create table users
{
    user_id
    user_name
    wait_action
    status
    last_balance_mes_id
    last_login
    registration
};

create table coins_code
{
    coin_code
    coin_id
};

create table users_notification
{
    user_id
    array {json(
        coin_code
        price
        description    
    )}
};

create table premium
{
    prem_id
    usd
    rub
    stars
};

create table premium
{
    lang_code
    description
};