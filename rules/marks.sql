-- Marks on valid orders. They are counted and are in no sum: a late order is a valid order.
--   late          it was received when its day was closed already
--   out_of_order  an order with a lower number was placed later
--   more          it has fields that nobody knows
select v.place,
       case when a.received_us >= v.closes_us then 1 else 0 end as late,
       case when a.placed_us < max(a.placed_us) over (
                   partition by a.shop order by a.n rows between unbounded preceding and 1 preceding)
            then 1 else 0 end as out_of_order,
       case when a.more_fields > 0 then 1 else 0 end as more
  from valid v
  join arrived a on a.place = v.place
 where v.why_not is null
