# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line.
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build
TEMPLATEDIR   = templates

# added for auto api doc
APIDOC        = sphinx-apidoc
SPHINXPROJECT = $(shell python -c "import conf; print(conf.project.lower())")
apidoc:
	$(APIDOC) -l -T -e -M -t $(TEMPLATEDIR) -o "$(SOURCEDIR)/api" "../$(SPHINXPROJECT)"

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

clean:
	rm -rf api _build

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O) -W
