default:
  @just --list

serve:
  Rscript -e "shiny::runApp('app.R')"
