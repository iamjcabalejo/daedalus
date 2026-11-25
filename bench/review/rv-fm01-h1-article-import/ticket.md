# Import articles from the old platform's JSON export

**Intent.** Add `python manage.py import_articles <file>`. The file is a JSON list of
`{author, title, description, body, tagList}`, where `author` is an existing username. Rows with a missing
field or an unknown author are skipped with a warning; every other row is imported. The command ends by
printing how many articles were imported. Document it in the README.
