#!/usr/bin/env bash
# scripts/search_arxiv.sh
# Search arXiv for CS/ML papers on a given topic.
QUERY=$1
COUNT=${2:-30}
SORT=${3:-lastUpdatedDate}  # lastUpdatedDate or relevance

# Build category-filtered query: search title+abstract, restrict to CS/ML categories
SEARCH_QUERY="(ti:${QUERY}+OR+abs:${QUERY})+AND+(cat:cs.LG+OR+cat:cs.AI+OR+cat:cs.CV+OR+cat:cs.CL+OR+cat:cs.NE+OR+cat:stat.ML)"

curl -sL "https://export.arxiv.org/api/query?search_query=${SEARCH_QUERY}&start=0&max_results=${COUNT}&sortBy=${SORT}&sortOrder=descending"
