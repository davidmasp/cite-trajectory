library(shiny)
library(DBI)
library(RSQLite)
library(dplyr)
library(ggplot2)
library(lubridate)
library(scales)

`%||%` <- function(x, y) {
  if (is.null(x)) y else x
}

default_db_path <- function() {
  candidates <- c(
    "data/openalex_citations.sqlite",
    "data/openalex_citations_test.sqlite"
  )
  existing <- candidates[file.exists(candidates)]
  if (length(existing) > 0) {
    existing[[1]]
  } else {
    candidates[[1]]
  }
}

connect_db <- function(db_path) {
  validate(need(nzchar(db_path), "Enter a SQLite database path."))
  validate(need(file.exists(db_path), paste("Database not found:", db_path)))
  dbConnect(SQLite(), dbname = db_path)
}

load_source_works <- function(db_path) {
  con <- connect_db(db_path)
  on.exit(dbDisconnect(con), add = TRUE)

  dbGetQuery(
    con,
    "
    select
      sw.source_id,
      sw.display_name,
      sw.publication_date,
      sw.source_name,
      sw.type,
      sw.cited_by_count,
      sw.api_list_count,
      count(ce.citing_work_id) as saved_citing_works
    from source_works sw
    left join citation_edges ce
      on ce.source_id = sw.source_id
    group by
      sw.source_id,
      sw.display_name,
      sw.publication_date,
      sw.source_name,
      sw.type,
      sw.cited_by_count,
      sw.api_list_count
    order by
      sw.publication_date,
      sw.display_name
    "
  )
}

load_filter_values <- function(db_path) {
  con <- connect_db(db_path)
  on.exit(dbDisconnect(con), add = TRUE)

  list(
    work_types = dbGetQuery(
      con,
      "select distinct type from citing_works where type is not null order by type"
    )$type,
    topic_domains = dbGetQuery(
      con,
      "
      select distinct primary_topic_domain_name
      from citing_works
      where primary_topic_domain_name is not null
      order by primary_topic_domain_name
      "
    )$primary_topic_domain_name,
    date_limits = dbGetQuery(
      con,
      "
      select
        min(publication_date) as min_date,
        max(publication_date) as max_date
      from citing_works
      where publication_date is not null
      "
    )
  )
}

sql_in_clause <- function(values) {
  paste(rep("?", length(values)), collapse = ", ")
}

load_plotting_data <- function(
  db_path,
  source_ids,
  work_types = character(),
  topic_domains = character(),
  date_range = NULL,
  exclude_imputed_jan1 = FALSE,
  include_retracted = FALSE,
  include_paratext = FALSE
) {
  validate(need(length(source_ids) >= 2, "Choose at least 2 source papers."))
  validate(need(length(source_ids) <= 5, "Choose no more than 5 source papers."))

  con <- connect_db(db_path)
  on.exit(dbDisconnect(con), add = TRUE)

  where_parts <- c(
    sprintf("ce.source_id in (%s)", sql_in_clause(source_ids)),
    "cw.publication_date is not null",
    "sw.publication_date is not null",
    "date(cw.publication_date) >= date(sw.publication_date)"
  )
  params <- as.list(source_ids)

  if (length(work_types) > 0) {
    where_parts <- c(where_parts, sprintf("cw.type in (%s)", sql_in_clause(work_types)))
    params <- c(params, as.list(work_types))
  }

  if (length(topic_domains) > 0) {
    where_parts <- c(
      where_parts,
      sprintf("cw.primary_topic_domain_name in (%s)", sql_in_clause(topic_domains))
    )
    params <- c(params, as.list(topic_domains))
  }

  if (isTRUE(exclude_imputed_jan1)) {
    where_parts <- c(where_parts, "strftime('%m-%d', cw.publication_date) <> '01-01'")
  }

  if (!isTRUE(include_retracted)) {
    where_parts <- c(where_parts, "coalesce(cw.is_retracted, 0) = 0")
  }

  if (!isTRUE(include_paratext)) {
    where_parts <- c(where_parts, "coalesce(cw.is_paratext, 0) = 0")
  }

  if (!is.null(date_range) && all(!is.na(date_range))) {
    where_parts <- c(
      where_parts,
      "date(cw.publication_date) between date(?) and date(?)"
    )
    params <- c(params, as.list(as.character(date_range)))
  }

  query <- sprintf(
    "
    with monthly as (
      select
        ce.source_id,
        sw.display_name as source_display_name,
        sw.publication_date as source_publication_date,
        sw.source_name as source_journal,
        sw.type as source_type,
        sw.cited_by_count as source_cited_by_count,
        sw.api_list_count as source_api_list_count,
        substr(cw.publication_date, 1, 7) || '-01' as month_start_date,
        count(*) as n_citations
      from citation_edges ce
      join source_works sw
        on sw.source_id = ce.source_id
      join citing_works cw
        on cw.work_id = ce.citing_work_id
      where %s
      group by
        ce.source_id,
        sw.display_name,
        sw.publication_date,
        sw.source_name,
        sw.type,
        sw.cited_by_count,
        sw.api_list_count,
        month_start_date
    )
    select
      source_id,
      source_display_name,
      source_publication_date,
      source_journal,
      source_type,
      source_cited_by_count,
      source_api_list_count,
      month_start_date,
      n_citations,
      sum(n_citations) over (
        partition by source_id
        order by month_start_date
        rows between unbounded preceding and current row
      ) as cumulative_citations
    from monthly
    order by source_id, month_start_date
    ",
    paste(where_parts, collapse = "\n        and ")
  )

  dbGetQuery(con, query, params = params) |>
    mutate(
      month_start_date = as.Date(month_start_date),
      source_publication_date = as.Date(source_publication_date),
      label = if_else(
        is.na(source_display_name) | source_display_name == "",
        source_id,
        source_display_name
      )
    )
}

plot_monthly_citations <- function(plot_data) {
  ggplot(plot_data, aes(x = month_start_date, y = n_citations, color = label)) +
    geom_point(alpha = 0.35, size = 1.8) +
    geom_smooth(method = "loess", span = 0.35, linewidth = 1.1, se = FALSE) +
    scale_color_brewer(palette = "Set1") +
    scale_x_date(labels = label_date_short()) +
    scale_y_continuous(labels = label_comma(), expand = expansion(mult = c(0, 0.05))) +
    labs(x = NULL, y = "Number of citations per month", color = "Paper") +
    theme_classic(base_size = 12) +
    theme(
      legend.position = "top",
      legend.direction = "vertical",
      legend.key.size = unit(0.12, "in"),
      plot.margin = margin(12, 16, 12, 12)
    )
}

plot_cumulative_citations <- function(plot_data) {
  ggplot(plot_data, aes(x = month_start_date, y = cumulative_citations, color = label)) +
    geom_line(linewidth = 1) +
    geom_point(alpha = 0.25, size = 1.3) +
    scale_color_brewer(palette = "Set1") +
    scale_x_date(labels = label_date_short()) +
    scale_y_continuous(labels = label_comma(), expand = expansion(mult = c(0, 0.05))) +
    labs(x = NULL, y = "Total citations", color = "Paper") +
    theme_classic(base_size = 12) +
    theme(
      legend.position = "top",
      legend.direction = "vertical",
      legend.key.size = unit(0.12, "in"),
      plot.margin = margin(12, 16, 12, 12)
    )
}

ui <- fluidPage(
  tags$head(
    tags$style(HTML(
      "
      body {
        background: #f7f7f5;
        color: #202124;
      }
      .container-fluid {
        max-width: 1320px;
      }
      .app-header {
        padding: 22px 0 8px;
      }
      .app-header h1 {
        margin: 0;
        font-size: 26px;
        font-weight: 650;
      }
      .app-header p {
        margin: 6px 0 0;
        color: #5f6368;
      }
      .sidebar-panel {
        background: #ffffff;
        border: 1px solid #dedede;
        border-radius: 8px;
        padding: 16px;
      }
      .plot-panel {
        background: #ffffff;
        border: 1px solid #dedede;
        border-radius: 8px;
        padding: 12px 14px 4px;
      }
      .summary-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 10px;
        margin: 0 0 12px;
      }
      .metric {
        background: #ffffff;
        border: 1px solid #dedede;
        border-radius: 8px;
        padding: 10px 12px;
      }
      .metric-label {
        color: #5f6368;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0;
      }
      .metric-value {
        font-size: 23px;
        font-weight: 650;
        margin-top: 2px;
      }
      .source-table {
        font-size: 13px;
      }
      .control-label {
        font-weight: 600;
      }
      "
    ))
  ),
  div(
    class = "app-header",
    h1("OpenAlex Citation Trajectories"),
    p("Select 2 to 5 extracted source papers from the local SQLite database.")
  ),
  sidebarLayout(
    sidebarPanel(
      width = 3,
      div(
        class = "sidebar-panel",
        textInput("db_path", "SQLite database", value = default_db_path()),
        actionButton("reload_db", "Load database", class = "btn-primary"),
        hr(),
        uiOutput("source_selector"),
        radioButtons(
          "plot_view",
          "Plot",
          choices = c("Monthly citations" = "monthly", "Cumulative citations" = "cumulative"),
          selected = "monthly"
        ),
        uiOutput("date_filter"),
        uiOutput("work_type_filter"),
        uiOutput("topic_domain_filter"),
        checkboxInput(
          "exclude_imputed_jan1",
          "Exclude likely imputed Jan 1 dates",
          value = FALSE
        ),
        checkboxInput("include_retracted", "Include retracted citing works", value = FALSE),
        checkboxInput("include_paratext", "Include paratext citing works", value = FALSE),
        downloadButton("download_data", "Download plotting data"),
        downloadButton("download_plot", "Download plot")
      )
    ),
    mainPanel(
      width = 9,
      uiOutput("status_message"),
      div(
        class = "summary-grid",
        div(class = "metric", div(class = "metric-label", "Selected papers"), div(class = "metric-value", textOutput("selected_count", inline = TRUE))),
        div(class = "metric", div(class = "metric-label", "Plotting rows"), div(class = "metric-value", textOutput("plotting_rows", inline = TRUE))),
        div(class = "metric", div(class = "metric-label", "Citing works"), div(class = "metric-value", textOutput("total_citations", inline = TRUE)))
      ),
      div(class = "plot-panel", plotOutput("citation_plot", height = "560px")),
      h4("Selected Source Papers"),
      div(class = "source-table", tableOutput("source_summary"))
    )
  )
)

server <- function(input, output, session) {
  active_db <- reactiveVal(default_db_path())

  observeEvent(input$reload_db, {
    active_db(input$db_path)
  })

  sources <- reactive({
    load_source_works(active_db())
  })

  filters <- reactive({
    load_filter_values(active_db())
  })

  output$source_selector <- renderUI({
    source_data <- sources()
    choices <- setNames(
      source_data$source_id,
      paste0(source_data$display_name, " (", source_data$source_id, ")")
    )

    selectizeInput(
      "source_ids",
      "Source papers",
      choices = choices,
      selected = head(source_data$source_id, min(5, nrow(source_data))),
      multiple = TRUE,
      options = list(maxItems = 5, plugins = list("remove_button"))
    )
  })

  output$date_filter <- renderUI({
    limits <- filters()$date_limits
    if (nrow(limits) == 0 || is.na(limits$min_date) || is.na(limits$max_date)) {
      return(NULL)
    }

    dateRangeInput(
      "date_range",
      "Citing publication dates",
      start = as.Date(limits$min_date),
      end = as.Date(limits$max_date),
      min = as.Date(limits$min_date),
      max = as.Date(limits$max_date)
    )
  })

  output$work_type_filter <- renderUI({
    values <- filters()$work_types
    if (length(values) == 0) {
      return(NULL)
    }

    selectizeInput(
      "work_types",
      "Citing work types",
      choices = values,
      selected = values,
      multiple = TRUE,
      options = list(plugins = list("remove_button"))
    )
  })

  output$topic_domain_filter <- renderUI({
    values <- filters()$topic_domains
    if (length(values) == 0) {
      return(NULL)
    }

    selectizeInput(
      "topic_domains",
      "Topic domains",
      choices = values,
      selected = values,
      multiple = TRUE,
      options = list(plugins = list("remove_button"))
    )
  })

  selected_sources <- reactive({
    source_data <- sources()
    req(input$source_ids)
    source_data |>
      filter(source_id %in% input$source_ids) |>
      arrange(match(source_id, input$source_ids))
  })

  valid_source_selection <- reactive({
    selected_count <- length(input$source_ids %||% character())
    selected_count >= 2 && selected_count <= 5
  })

  plotting_data <- reactive({
    req(input$source_ids)
    load_plotting_data(
      db_path = active_db(),
      source_ids = input$source_ids,
      work_types = input$work_types,
      topic_domains = input$topic_domains,
      date_range = input$date_range,
      exclude_imputed_jan1 = isTRUE(input$exclude_imputed_jan1),
      include_retracted = input$include_retracted,
      include_paratext = input$include_paratext
    )
  })

  selected_plot <- reactive({
    data <- plotting_data()
    validate(need(nrow(data) > 0, "No citation rows match the current selection."))

    if (identical(input$plot_view, "cumulative")) {
      plot_cumulative_citations(data)
    } else {
      plot_monthly_citations(data)
    }
  })

  output$status_message <- renderUI({
    source_data <- sources()
    if (nrow(source_data) < 2) {
      div(
        class = "alert alert-warning",
        paste(
          "This database has",
          nrow(source_data),
          "source paper. Add at least one more extracted source paper before comparison plots can be drawn."
        )
      )
    } else if (!valid_source_selection()) {
      div(
        class = "alert alert-info",
        "Choose 2 to 5 source papers to draw the comparison plot."
      )
    } else {
      NULL
    }
  })

  output$selected_count <- renderText({
    length(input$source_ids %||% character())
  })

  output$plotting_rows <- renderText({
    if (!valid_source_selection()) {
      return("0")
    }
    comma(nrow(plotting_data()))
  })

  output$total_citations <- renderText({
    if (!valid_source_selection()) {
      return("0")
    }
    comma(sum(plotting_data()$n_citations))
  })

  output$citation_plot <- renderPlot({
    selected_plot()
  }, res = 120)

  output$source_summary <- renderTable({
    selected_sources() |>
      transmute(
        `OpenAlex ID` = source_id,
        Title = display_name,
        Published = publication_date,
        Journal = source_name,
        Type = type,
        `Saved citing works` = saved_citing_works,
        `OpenAlex cited_by_count` = cited_by_count,
        `OpenAlex list count` = api_list_count
      )
  }, striped = TRUE, bordered = TRUE, spacing = "s")

  output$download_data <- downloadHandler(
    filename = function() {
      paste0("openalex_citation_plotting_data_", Sys.Date(), ".csv")
    },
    content = function(file) {
      write.csv(plotting_data(), file, row.names = FALSE)
    }
  )

  output$download_plot <- downloadHandler(
    filename = function() {
      suffix <- if (identical(input$plot_view, "cumulative")) "cumulative" else "monthly"
      paste0("openalex_citation_", suffix, "_plot_", Sys.Date(), ".png")
    },
    content = function(file) {
      ggsave(file, selected_plot(), width = 11, height = 7, dpi = 300)
    }
  )
}

shinyApp(ui, server)
