-- Why a line is not a valid order. The first reason that fits counts, and none means that it is one.
-- An event is named by its feed and its id, an order by its feed and its number. Both names are fingerprints here, because engines
-- have opinions of their own about large and small letters. Each feed belongs to one shop.
with judged as (
  select a.place, a.shop, a.n, a.event_print, a.body_print, a.received_us, a.says, a.order_print, a.placed_us
    from arrived a
    join lines l on l.place = a.place
   where l.standing = 'stands'
),
events as (
  select j.place, j.shop, j.n, j.body_print, j.received_us, j.says, j.order_print, j.placed_us,
         row_number() over (partition by j.shop, j.event_print order by j.n) as of_its_id,
         first_value(j.body_print) over (partition by j.shop, j.event_print order by j.n) as first_body
    from judged j
),
orders as (
  -- Whoever comes first with a number has it, even if that order is not valid for another reason.
  select place, row_number() over (partition by shop, order_print order by n) as of_its_number
    from events
   where of_its_id = 1 and says = 'order'
)
select e.place, d.shop_day, d.closes_us,
       case when e.of_its_id > 1 and e.body_print = e.first_body  then 'the same event'
            when e.of_its_id > 1                                  then 'another body'
            when e.says <> 'order'                                then e.says
            when e.placed_us > e.received_us + x.future_us        then 'from the future'
            when e.placed_us < e.received_us - x.oldest_us        then 'too old'
            when d.shop_day is null                               then 'no day for this shop'
            when o.of_its_number > 1                              then 'number used'
       end as why_not
  from events e
 cross join limits x
  left join orders o on o.place = e.place
  left join shop_days d on d.shop = e.shop and e.placed_us >= d.from_us and e.placed_us < d.to_us
