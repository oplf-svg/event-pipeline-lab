-- What each line that arrived is.
--   spoiled                  its fingerprint does not fit, or it cannot be read. It takes no number
--   contradicts              two different lines have this number and both fingerprints fit, so nobody can say which one is right
--   the same line            it was there already
--   behind a missing number  a number before it is not there
--   behind a contradiction   nobody can say what stands before it
--   stands                   all others. They are judged, in the order of their numbers and not in the order in which they arrived
with numbers as (
  select shop, n, min(place) as place, count(distinct line_print) as different_lines
    from arrived
   where spoiled = 0
   group by shop, n
),
in_order as (
  -- As long as none is missing, a number is its own rank.
  select shop, n, place, different_lines,
         row_number() over (partition by shop order by n) as rank_of_n,
         max(different_lines) over (partition by shop order by n rows between unbounded preceding and current row) as most_lines
    from numbers
)
select a.place,
       case when a.spoiled = 1            then 'spoiled'
            when i.different_lines > 1    then 'contradicts'
            when a.place <> i.place       then 'the same line'
            when i.n <> i.rank_of_n       then 'behind a missing number'
            when i.most_lines > 1         then 'behind a contradiction'
            else                               'stands'
       end as standing
  from arrived a
  left join in_order i on i.shop = a.shop and i.n = a.n
