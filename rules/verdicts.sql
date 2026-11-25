-- One verdict for each line that arrived: raw = valid + duplicate + bad + waiting.
select l.place, a.shop, a.n,
       case when l.standing in ('behind a missing number', 'behind a contradiction') then 'waiting'
            when l.standing = 'the same line'   then 'duplicate'
            when l.standing <> 'stands'         then 'bad'
            when v.why_not = 'the same event'   then 'duplicate'
            when v.why_not is not null          then 'bad'
            else                                     'valid'
       end as verdict,
       case when l.standing <> 'stands'         then l.standing
            else                                     coalesce(v.why_not, 'an order')
       end as reason,
       case when m.place is null then null else v.shop_day end as shop_day,
       case when m.place is null then 0 else a.cents end as cents,
       coalesce(m.late, 0) as late, coalesce(m.out_of_order, 0) as out_of_order, coalesce(m.more, 0) as more, a.received_us
  from lines l
  join arrived a on a.place = l.place
  left join valid v on v.place = l.place
  left join marks m on m.place = l.place
