ASOF ?= 2026-08
refresh: ; python run.py refresh --source $${SOURCE:-local}
month:   ; python run.py month --asof $(ASOF)
publish: ; python run.py publish --asof $(ASOF)
test:    ; python -m pytest tests/ -q
