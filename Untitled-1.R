
library(ggplot2)

ed1_dat = readr::read_csv("./hallmarks_og_works-csv-H3e6RcrEAdxdqE7YbYznjr.csv")
ed2_dat = readr::read_csv("./hallmarks_nextgen_works-csv-W356rk5THXd9pRNgLYPNZ3.csv")
ed3_dat = readr::read_csv("./hallmarks_newdimensions_works-csv-6gXeJ4rmhpsvBSDEw37HFS.csv")
ed1_dat$pubdate = "2000-01-07" |> lubridate::date()
ed2_dat$pubdate = "2011-04-03" |> lubridate::date()
ed3_dat$pubdate = "2022-01-12" |> lubridate::date()
ed1_dat$journal_original = "Cell"
ed2_dat$journal_original = "Cell"
ed3_dat$journal_original = "Cancer Discovery"
ed1_dat$edition = "00' HoC"
ed2_dat$edition = "11' HoC - The Next Generation"
ed3_dat$edition = "22' HoC - New Dimensions"

dat = dplyr::bind_rows(ed1_dat, ed2_dat, ed3_dat)

# include types ----------------------------------------------------------

ids = dat$id |> stringr::str_extract("W\\d+")
url_req = glue::glue("https://api.openalex.org/works/{ids}?select=id,topics,type")

library(progress)
pb = progress::progress_bar$new(
  total = length(url_req),
  format = "[:bar] :current/:total (:percent) ETA: :eta"
)

url_req |> purrr::map(function(x){
  pb$tick()
  req <- httr2::request(x)
  resp <- httr2::req_perform(req)
  resp |> httr2::resp_body_json(simplifyVector = TRUE) -> r_json
  # sleep 0.1
  Sys.sleep(0.01)
  #print(x)
  r_json
  r_json$isLS = ifelse("Life Sciences" %in% r_json$topics$domain$display_name,
          "Life Sciences", "Other")
  r_json
}) -> responses

types = responses |> purrr::map_chr("type")

# rest of the script ----------------------------------------------------------

dat$date = dat$publication_date |> lubridate::date()
dat = dat |> dplyr::filter(pubdate <= date)

month_date = lubridate::month(dat$date)
year_date = lubridate::year(dat$date)

dat$start_date = lubridate::date(glue::glue("{year_date}-{month_date}-01"))

# for some reason january citations are overblown.
#dat = dat |> dplyr::filter(month_date != 1)

dat |> 
  dplyr::group_by(start_date, edition , journal_original) |> 
  dplyr::summarise(n = dplyr::n()) -> summ_dat

summ_dat |>
  dplyr::arrange(start_date) |>
  dplyr::group_by(edition) |> 
  dplyr::mutate(cum_n = cumsum(n)) -> summ_dat

# plot ----------------------------------------------------------

ggplot(summ_dat, aes(x=start_date, y=n, color=edition)) +
  geom_point(alpha= 0.3) +
  geom_smooth(method = "loess", span = 0.35, linewidth = 1.5, se=FALSE) + 
  scale_color_brewer(palette = "Set1") +
  labs(x = "", y = "Number of Citations per Month", color = "Edition") + 
  theme_classic() +
  theme(
    text = element_text(size=8),
    legend.position = "top",
    legend.key.size = unit(0.1, "in"),
    legend.direction = "vertical") +
  scale_y_continuous(expand = expansion(mult = c(0, 0.05))) 


# plot 2 ----------------------------------------------------------

ggplot(summ_dat, aes(x=start_date, y=cum_n, color=edition)) +
  geom_line() +
  scale_color_brewer(palette = "Set1") +
  labs(x = "", y = "Total Citations", color = "Edition") + 
  theme_classic() +
  theme(
    text = element_text(size=8),
    legend.position = "top",
    legend.key.size = unit(0.1, "in"),
    legend.direction = "vertical") +
  scale_y_continuous(expand = expansion(mult = c(0, 0.05)))


# test weird jan thing ----------------------------------------------------------

jan_dat = dat |> dplyr::filter(month_date == 1)

ids = jan_dat$id |> stringr::str_extract("W\\d+") 

ids |> sample(100) -> sample_ids

url_req = glue::glue("https://api.openalex.org/works/{sample_ids}?select=id,topics,type")

url_req |> purrr::map(function(x){
  req <- httr2::request(x)
  resp <- httr2::req_perform(req)
  resp |> httr2::resp_body_json(simplifyVector = TRUE) -> r_json
  # sleep 0.1
  Sys.sleep(0.2)
  print(x)
  r_json
}) -> responses

types = responses |> purrr::map_chr("type")
table(types)

# compare with types_normal
table(types_normal)
