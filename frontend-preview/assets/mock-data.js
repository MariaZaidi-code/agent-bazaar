window.MOCK_DATA = {
  "health": {
    "status": "ok",
    "app": "Agent Bazaar",
    "version": "0.1.0",
    "mode": "offline",
    "tools": 15,
    "llm_enabled": false
  },
  "tools": {
    "tools": [
      {
        "id": "arxiv-search",
        "name": "arXiv Research Search",
        "provider_id": "arxiv",
        "description": "Search recent research papers on arXiv by topic and return titles, summaries, authors and links.",
        "capability": "SearchResearchPapers",
        "inputs": [
          {
            "concept": "ResearchTopic",
            "name": "query",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "Research topic or keywords.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "ResearchPaper",
            "name": "papers",
            "unit": null,
            "datatype": "array",
            "required": true,
            "description": "Ranked paper records.",
            "fields": [
              "title",
              "summary",
              "url",
              "published",
              "authors"
            ]
          }
        ],
        "claims": [
          {
            "text": "Searches arXiv metadata without an API key.",
            "label": "Supported",
            "evidence": "arXiv API documentation.",
            "checked_at": null
          },
          {
            "text": "Returns titles, summaries and links.",
            "label": "Supported",
            "evidence": "arXiv Atom feed schema.",
            "checked_at": null
          }
        ],
        "keywords": [
          "research",
          "paper",
          "papers",
          "arxiv",
          "study",
          "literature",
          "graphrag",
          "ontology",
          "llm",
          "publication",
          "science"
        ],
        "docs_url": "https://info.arxiv.org/help/api/index.html",
        "price": 0.0,
        "probe_eligible": true,
        "execution": "live",
        "tags": [
          "api",
          "research",
          "backup-eligible"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "arxiv-search-backup",
        "name": "arXiv Research Search (Backup Mirror)",
        "provider_id": "arxiv-backup",
        "description": "Standby backup mirror used to test circuit-breaker substitution. Mirrors arXiv Research Search. Search recent research papers on arXiv by topic and return titles, summaries, authors and links.",
        "capability": "SearchResearchPapers",
        "inputs": [
          {
            "concept": "ResearchTopic",
            "name": "query",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "Research topic or keywords.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "ResearchPaper",
            "name": "papers",
            "unit": null,
            "datatype": "array",
            "required": true,
            "description": "Ranked paper records.",
            "fields": [
              "title",
              "summary",
              "url",
              "published",
              "authors"
            ]
          }
        ],
        "claims": [
          {
            "text": "Searches arXiv metadata without an API key.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          },
          {
            "text": "Returns titles, summaries and links.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          }
        ],
        "keywords": [
          "research",
          "paper",
          "papers",
          "arxiv",
          "study",
          "literature",
          "graphrag",
          "ontology",
          "llm",
          "publication",
          "science"
        ],
        "docs_url": "https://info.arxiv.org/help/api/index.html",
        "price": 0.0,
        "probe_eligible": false,
        "execution": "mock",
        "tags": [
          "api",
          "research",
          "backup-eligible",
          "backup"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "document-qa",
        "name": "Uploaded Document Question Answering",
        "provider_id": "document-service",
        "description": "Answer questions over a document uploaded by the developer, returning extractive citations from the document.",
        "capability": "AnswerFromDocument",
        "inputs": [
          {
            "concept": "DocumentQuestion",
            "name": "question",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "Question about the document.",
            "fields": []
          },
          {
            "concept": "DocumentReference",
            "name": "document_id",
            "unit": null,
            "datatype": "string",
            "required": false,
            "description": "Uploaded document identifier; the most recent document is used by default.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "AnswerFromDocument",
            "name": "answer",
            "unit": null,
            "datatype": "object",
            "required": true,
            "description": "Answer grounded in quoted document passages.",
            "fields": [
              "answer",
              "citations",
              "document_id"
            ]
          }
        ],
        "claims": [
          {
            "text": "Answers from the uploaded document with citations.",
            "label": "Supported",
            "evidence": "Local extractive QA implementation; every answer includes a passage.",
            "checked_at": null
          },
          {
            "text": "Does not send document text to a paid service.",
            "label": "Supported",
            "evidence": "Local parsing and retrieval; the optional LLM is disabled by default.",
            "checked_at": null
          }
        ],
        "keywords": [
          "document",
          "file",
          "uploaded",
          "upload",
          "pdf",
          "docx",
          "text",
          "according",
          "document says",
          "paper",
          "report",
          "notes"
        ],
        "docs_url": "",
        "price": 0.0,
        "probe_eligible": false,
        "execution": "live",
        "tags": [
          "document",
          "local"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "frankfurter-currency",
        "name": "Frankfurter Currency Converter",
        "provider_id": "frankfurter",
        "description": "Convert a monetary amount between currencies using keyless reference exchange rates.",
        "capability": "ConvertCurrency",
        "inputs": [
          {
            "concept": "MoneyAmount",
            "name": "amount",
            "unit": null,
            "datatype": "number",
            "required": true,
            "description": "Amount to convert.",
            "fields": []
          },
          {
            "concept": "CurrencyCode",
            "name": "from_currency",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "ISO 4217 source currency code.",
            "fields": []
          },
          {
            "concept": "CurrencyCode",
            "name": "to_currency",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "ISO 4217 target currency code.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "Money",
            "name": "conversion",
            "unit": null,
            "datatype": "object",
            "required": true,
            "description": "Converted amount and exchange rate.",
            "fields": [
              "amount",
              "currency",
              "rate",
              "from",
              "to",
              "date"
            ]
          }
        ],
        "claims": [
          {
            "text": "Converts an amount between supported currencies without an API key.",
            "label": "Supported",
            "evidence": "Frankfurter documentation; PKR is served by the documented keyless fallback.",
            "checked_at": null
          },
          {
            "text": "The output states the effective rate and date.",
            "label": "Supported",
            "evidence": "Provider response schema.",
            "checked_at": null
          }
        ],
        "keywords": [
          "currency",
          "exchange",
          "rate",
          "convert",
          "money",
          "usd",
          "pkr",
          "eur",
          "dollar",
          "rupee",
          "conversion"
        ],
        "docs_url": "https://www.frankfurter.app/docs/",
        "price": 0.0,
        "probe_eligible": true,
        "execution": "live",
        "tags": [
          "api",
          "finance",
          "backup-eligible"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "frankfurter-currency-backup",
        "name": "Frankfurter Currency Converter (Backup Mirror)",
        "provider_id": "frankfurter-backup",
        "description": "Standby backup mirror used to test circuit-breaker substitution. Mirrors Frankfurter Currency Converter. Convert a monetary amount between currencies using keyless reference exchange rates.",
        "capability": "ConvertCurrency",
        "inputs": [
          {
            "concept": "MoneyAmount",
            "name": "amount",
            "unit": null,
            "datatype": "number",
            "required": true,
            "description": "Amount to convert.",
            "fields": []
          },
          {
            "concept": "CurrencyCode",
            "name": "from_currency",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "ISO 4217 source currency code.",
            "fields": []
          },
          {
            "concept": "CurrencyCode",
            "name": "to_currency",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "ISO 4217 target currency code.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "Money",
            "name": "conversion",
            "unit": null,
            "datatype": "object",
            "required": true,
            "description": "Converted amount and exchange rate.",
            "fields": [
              "amount",
              "currency",
              "rate",
              "from",
              "to",
              "date"
            ]
          }
        ],
        "claims": [
          {
            "text": "Converts an amount between supported currencies without an API key.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          },
          {
            "text": "The output states the effective rate and date.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          }
        ],
        "keywords": [
          "currency",
          "exchange",
          "rate",
          "convert",
          "money",
          "usd",
          "pkr",
          "eur",
          "dollar",
          "rupee",
          "conversion"
        ],
        "docs_url": "https://www.frankfurter.app/docs/",
        "price": 0.0,
        "probe_eligible": false,
        "execution": "mock",
        "tags": [
          "api",
          "finance",
          "backup-eligible",
          "backup"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "mock-weather-fahrenheit",
        "name": "Mock Weather Adversary",
        "provider_id": "mock-weather-fahrenheit",
        "description": "A deliberately misleading weather tool that claims Celsius but returns Fahrenheit values, used to test claim badges and unit checks.",
        "capability": "GetWeatherForecast",
        "inputs": [
          {
            "concept": "Coordinates",
            "name": "coordinates",
            "unit": "degrees",
            "datatype": "object",
            "required": true,
            "description": "Latitude and longitude.",
            "fields": []
          },
          {
            "concept": "DateTimeISO",
            "name": "date",
            "unit": null,
            "datatype": "string",
            "required": false,
            "description": "ISO date.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "Temperature",
            "name": "forecast",
            "unit": "F",
            "datatype": "object",
            "required": true,
            "description": "Forecast values in Fahrenheit despite the Celsius claim.",
            "fields": [
              "temperature",
              "temp_max",
              "temp_min",
              "unit"
            ]
          }
        ],
        "claims": [
          {
            "text": "Returns temperature in Celsius.",
            "label": "Contradicted",
            "evidence": "Seeded adversarial provider: the payload unit is Fahrenheit.",
            "checked_at": null
          },
          {
            "text": "No API key is required.",
            "label": "Verified",
            "evidence": "Mock provider is local.",
            "checked_at": null
          }
        ],
        "keywords": [
          "weather",
          "temperature",
          "mock",
          "fahrenheit",
          "unreliable",
          "forecast"
        ],
        "docs_url": "",
        "price": 0.0,
        "probe_eligible": true,
        "execution": "mock",
        "tags": [
          "mock",
          "adversarial",
          "weather"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "nager-holidays",
        "name": "Nager.Date Public Holidays",
        "provider_id": "nager-date",
        "description": "List public holidays for a country and year, including local names and dates.",
        "capability": "GetPublicHolidays",
        "inputs": [
          {
            "concept": "CountryCode",
            "name": "country_code",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "ISO 3166-1 alpha-2 country code.",
            "fields": []
          },
          {
            "concept": "Number",
            "name": "year",
            "unit": null,
            "datatype": "integer",
            "required": true,
            "description": "Calendar year.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "Holiday",
            "name": "holidays",
            "unit": null,
            "datatype": "array",
            "required": true,
            "description": "Public holidays for the requested country and year.",
            "fields": [
              "date",
              "name",
              "local_name",
              "country_code"
            ]
          }
        ],
        "claims": [
          {
            "text": "Returns public holidays by country and year.",
            "label": "Supported",
            "evidence": "Nager.Date API documentation.",
            "checked_at": null
          },
          {
            "text": "No API key is required.",
            "label": "Supported",
            "evidence": "Nager.Date public endpoint.",
            "checked_at": null
          }
        ],
        "keywords": [
          "holiday",
          "holidays",
          "public holiday",
          "national holiday",
          "calendar",
          "eid",
          "christmas",
          "pakistan",
          "country"
        ],
        "docs_url": "https://date.nager.at/Api",
        "price": 0.0,
        "probe_eligible": true,
        "execution": "live",
        "tags": [
          "api",
          "calendar",
          "backup-eligible"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "nager-holidays-backup",
        "name": "Nager.Date Public Holidays (Backup Mirror)",
        "provider_id": "nager-date-backup",
        "description": "Standby backup mirror used to test circuit-breaker substitution. Mirrors Nager.Date Public Holidays. List public holidays for a country and year, including local names and dates.",
        "capability": "GetPublicHolidays",
        "inputs": [
          {
            "concept": "CountryCode",
            "name": "country_code",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "ISO 3166-1 alpha-2 country code.",
            "fields": []
          },
          {
            "concept": "Number",
            "name": "year",
            "unit": null,
            "datatype": "integer",
            "required": true,
            "description": "Calendar year.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "Holiday",
            "name": "holidays",
            "unit": null,
            "datatype": "array",
            "required": true,
            "description": "Public holidays for the requested country and year.",
            "fields": [
              "date",
              "name",
              "local_name",
              "country_code"
            ]
          }
        ],
        "claims": [
          {
            "text": "Returns public holidays by country and year.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          },
          {
            "text": "No API key is required.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          }
        ],
        "keywords": [
          "holiday",
          "holidays",
          "public holiday",
          "national holiday",
          "calendar",
          "eid",
          "christmas",
          "pakistan",
          "country"
        ],
        "docs_url": "https://date.nager.at/Api",
        "price": 0.0,
        "probe_eligible": false,
        "execution": "mock",
        "tags": [
          "api",
          "calendar",
          "backup-eligible",
          "backup"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "nominatim-geocode",
        "name": "OpenStreetMap Nominatim Geocoder",
        "provider_id": "nominatim",
        "description": "Resolve a city or place name to latitude, longitude and a display name using the public OpenStreetMap Nominatim search API.",
        "capability": "GeocodeLocation",
        "inputs": [
          {
            "concept": "LocationName",
            "name": "location",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "City, address or place name to resolve.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "Coordinates",
            "name": "coordinates",
            "unit": "degrees",
            "datatype": "object",
            "required": true,
            "description": "WGS84 coordinates for the resolved place.",
            "fields": [
              "latitude",
              "longitude",
              "display_name",
              "country_code"
            ]
          }
        ],
        "claims": [
          {
            "text": "Resolves place names without an API key.",
            "label": "Verified",
            "evidence": "Seeded demo evidence from the public Nominatim endpoint; the live Auditor replaces this.",
            "checked_at": null
          },
          {
            "text": "Returns coordinates in WGS84 degrees.",
            "label": "Supported",
            "evidence": "Nominatim API documentation.",
            "checked_at": null
          }
        ],
        "keywords": [
          "geocode",
          "geocoding",
          "location",
          "city",
          "place",
          "map",
          "coordinates",
          "latitude",
          "longitude",
          "address"
        ],
        "docs_url": "https://nominatim.org/release-docs/latest/api/Search/",
        "price": 0.0,
        "probe_eligible": true,
        "execution": "live",
        "tags": [
          "api",
          "geospatial",
          "backup-eligible"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "nominatim-geocode-backup",
        "name": "OpenStreetMap Nominatim Geocoder (Backup Mirror)",
        "provider_id": "nominatim-backup",
        "description": "Standby backup mirror used to test circuit-breaker substitution. Mirrors OpenStreetMap Nominatim Geocoder. Resolve a city or place name to latitude, longitude and a display name using the public OpenStreetMap Nominatim search API.",
        "capability": "GeocodeLocation",
        "inputs": [
          {
            "concept": "LocationName",
            "name": "location",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "City, address or place name to resolve.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "Coordinates",
            "name": "coordinates",
            "unit": "degrees",
            "datatype": "object",
            "required": true,
            "description": "WGS84 coordinates for the resolved place.",
            "fields": [
              "latitude",
              "longitude",
              "display_name",
              "country_code"
            ]
          }
        ],
        "claims": [
          {
            "text": "Resolves place names without an API key.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          },
          {
            "text": "Returns coordinates in WGS84 degrees.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          }
        ],
        "keywords": [
          "geocode",
          "geocoding",
          "location",
          "city",
          "place",
          "map",
          "coordinates",
          "latitude",
          "longitude",
          "address"
        ],
        "docs_url": "https://nominatim.org/release-docs/latest/api/Search/",
        "price": 0.0,
        "probe_eligible": false,
        "execution": "mock",
        "tags": [
          "api",
          "geospatial",
          "backup-eligible",
          "backup"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "open-meteo-forecast",
        "name": "Open-Meteo Weather Forecast",
        "provider_id": "open-meteo",
        "description": "Return a daily weather forecast with maximum and minimum temperature, rain probability and timezone for a coordinate pair.",
        "capability": "GetWeatherForecast",
        "inputs": [
          {
            "concept": "Coordinates",
            "name": "coordinates",
            "unit": "degrees",
            "datatype": "object",
            "required": true,
            "description": "Latitude and longitude from a geocoder.",
            "fields": []
          },
          {
            "concept": "DateTimeISO",
            "name": "date",
            "unit": null,
            "datatype": "string",
            "required": false,
            "description": "ISO date to forecast; tomorrow by default.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "Temperature",
            "name": "forecast",
            "unit": "C",
            "datatype": "object",
            "required": true,
            "description": "Daily forecast values in degrees Celsius.",
            "fields": [
              "temperature",
              "temp_max",
              "temp_min",
              "precipitation_probability",
              "date",
              "timezone"
            ]
          }
        ],
        "claims": [
          {
            "text": "Returns temperatures in Celsius.",
            "label": "Verified",
            "evidence": "Seeded demo evidence from the public forecast endpoint; the live Auditor replaces this.",
            "checked_at": null
          },
          {
            "text": "No API key is required.",
            "label": "Verified",
            "evidence": "Open-Meteo free endpoint documentation.",
            "checked_at": null
          },
          {
            "text": "Provides a daily forecast for the requested location.",
            "label": "Supported",
            "evidence": "Open-Meteo forecast API documentation.",
            "checked_at": null
          }
        ],
        "keywords": [
          "weather",
          "temperature",
          "forecast",
          "rain",
          "precipitation",
          "tomorrow",
          "celsius",
          "hot",
          "cold",
          "climate"
        ],
        "docs_url": "https://open-meteo.com/en/docs",
        "price": 0.0,
        "probe_eligible": true,
        "execution": "live",
        "tags": [
          "api",
          "weather",
          "backup-eligible"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "open-meteo-forecast-backup",
        "name": "Open-Meteo Weather Forecast (Backup Mirror)",
        "provider_id": "open-meteo-backup",
        "description": "Standby backup mirror used to test circuit-breaker substitution. Mirrors Open-Meteo Weather Forecast. Return a daily weather forecast with maximum and minimum temperature, rain probability and timezone for a coordinate pair.",
        "capability": "GetWeatherForecast",
        "inputs": [
          {
            "concept": "Coordinates",
            "name": "coordinates",
            "unit": "degrees",
            "datatype": "object",
            "required": true,
            "description": "Latitude and longitude from a geocoder.",
            "fields": []
          },
          {
            "concept": "DateTimeISO",
            "name": "date",
            "unit": null,
            "datatype": "string",
            "required": false,
            "description": "ISO date to forecast; tomorrow by default.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "Temperature",
            "name": "forecast",
            "unit": "C",
            "datatype": "object",
            "required": true,
            "description": "Daily forecast values in degrees Celsius.",
            "fields": [
              "temperature",
              "temp_max",
              "temp_min",
              "precipitation_probability",
              "date",
              "timezone"
            ]
          }
        ],
        "claims": [
          {
            "text": "Returns temperatures in Celsius.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          },
          {
            "text": "No API key is required.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          },
          {
            "text": "Provides a daily forecast for the requested location.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          }
        ],
        "keywords": [
          "weather",
          "temperature",
          "forecast",
          "rain",
          "precipitation",
          "tomorrow",
          "celsius",
          "hot",
          "cold",
          "climate"
        ],
        "docs_url": "https://open-meteo.com/en/docs",
        "price": 0.0,
        "probe_eligible": false,
        "execution": "mock",
        "tags": [
          "api",
          "weather",
          "backup-eligible",
          "backup"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "restcountries-facts",
        "name": "REST Countries Fact Service",
        "provider_id": "rest-countries",
        "description": "Return country facts such as capital, population, region and currencies by country name.",
        "capability": "GetCountryFacts",
        "inputs": [
          {
            "concept": "CountryName",
            "name": "country",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "Country name to look up.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "Country",
            "name": "country",
            "unit": null,
            "datatype": "object",
            "required": true,
            "description": "Country facts.",
            "fields": [
              "name",
              "capital",
              "population",
              "region",
              "currencies",
              "country_code"
            ]
          }
        ],
        "claims": [
          {
            "text": "Returns population and capital without an API key.",
            "label": "Supported",
            "evidence": "REST Countries public API documentation.",
            "checked_at": null
          },
          {
            "text": "Returns ISO country codes.",
            "label": "Supported",
            "evidence": "REST Countries response schema.",
            "checked_at": null
          }
        ],
        "keywords": [
          "country",
          "population",
          "capital",
          "nation",
          "facts",
          "region",
          "currency",
          "japan",
          "pakistan",
          "germany"
        ],
        "docs_url": "https://restcountries.com/",
        "price": 0.0,
        "probe_eligible": true,
        "execution": "live",
        "tags": [
          "api",
          "reference",
          "backup-eligible"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "restcountries-facts-backup",
        "name": "REST Countries Fact Service (Backup Mirror)",
        "provider_id": "rest-countries-backup",
        "description": "Standby backup mirror used to test circuit-breaker substitution. Mirrors REST Countries Fact Service. Return country facts such as capital, population, region and currencies by country name.",
        "capability": "GetCountryFacts",
        "inputs": [
          {
            "concept": "CountryName",
            "name": "country",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "Country name to look up.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "Country",
            "name": "country",
            "unit": null,
            "datatype": "object",
            "required": true,
            "description": "Country facts.",
            "fields": [
              "name",
              "capital",
              "population",
              "region",
              "currencies",
              "country_code"
            ]
          }
        ],
        "claims": [
          {
            "text": "Returns population and capital without an API key.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          },
          {
            "text": "Returns ISO country codes.",
            "label": "Unsupported",
            "evidence": "Backup mirror; not independently verified.",
            "checked_at": null
          }
        ],
        "keywords": [
          "country",
          "population",
          "capital",
          "nation",
          "facts",
          "region",
          "currency",
          "japan",
          "pakistan",
          "germany"
        ],
        "docs_url": "https://restcountries.com/",
        "price": 0.0,
        "probe_eligible": false,
        "execution": "mock",
        "tags": [
          "api",
          "reference",
          "backup-eligible",
          "backup"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      },
      {
        "id": "university-sql",
        "name": "University Read-only SQL Provider",
        "provider_id": "university-db",
        "description": "Answer questions about students, programs, courses and enrolment using a local read-only university SQL database.",
        "capability": "QueryStructuredData",
        "inputs": [
          {
            "concept": "NaturalLanguageQuery",
            "name": "question",
            "unit": null,
            "datatype": "string",
            "required": true,
            "description": "Question about the sample university database.",
            "fields": []
          }
        ],
        "outputs": [
          {
            "concept": "TabularAnswer",
            "name": "table",
            "unit": null,
            "datatype": "object",
            "required": true,
            "description": "Query result rows with the SQL that produced them.",
            "fields": [
              "columns",
              "rows",
              "sql",
              "row_count"
            ]
          }
        ],
        "claims": [
          {
            "text": "Uses a read-only connection to the local sample database.",
            "label": "Verified",
            "evidence": "Enforced in the Provider with a query-only connection.",
            "checked_at": null
          },
          {
            "text": "Rejects writes and non-allow-listed tables.",
            "label": "Verified",
            "evidence": "SQL guard and allow-list checked before execution.",
            "checked_at": null
          }
        ],
        "keywords": [
          "database",
          "sql",
          "students",
          "student",
          "program",
          "programs",
          "enrolment",
          "enrollment",
          "gpa",
          "courses",
          "university",
          "count",
          "rows"
        ],
        "docs_url": "",
        "price": 0.0,
        "probe_eligible": true,
        "execution": "live",
        "tags": [
          "database",
          "local"
        ],
        "trust": 0.5,
        "demoted": false,
        "breaker": "closed",
        "validation": []
      }
    ],
    "count": 15
  },
  "ontology": {
    "summary": {
      "version": "0.1-local",
      "concepts": 27,
      "units": 13,
      "capabilities": 8,
      "violations": []
    },
    "concepts": [
      {
        "concept": "AnswerFromDocument",
        "parents": [
          "Entity"
        ],
        "description": "An extractive answer grounded in a document.",
        "fields": [
          "answer",
          "citations",
          "document_id"
        ]
      },
      {
        "concept": "Capability",
        "parents": [
          "Entity"
        ],
        "description": "What a service can do.",
        "fields": []
      },
      {
        "concept": "CityName",
        "parents": [
          "LocationName"
        ],
        "description": "A city or settlement name.",
        "fields": []
      },
      {
        "concept": "Claim",
        "parents": [
          "Entity"
        ],
        "description": "A provider statement about its service.",
        "fields": []
      },
      {
        "concept": "Coordinates",
        "parents": [
          "Entity"
        ],
        "description": "A latitude and longitude pair.",
        "fields": [
          "latitude",
          "longitude",
          "display_name",
          "country_code"
        ]
      },
      {
        "concept": "Country",
        "parents": [
          "Entity"
        ],
        "description": "A country and its public facts.",
        "fields": [
          "name",
          "capital",
          "population",
          "region",
          "currencies",
          "country_code"
        ]
      },
      {
        "concept": "CountryCode",
        "parents": [
          "Entity"
        ],
        "description": "An ISO 3166 country code.",
        "fields": []
      },
      {
        "concept": "CountryName",
        "parents": [
          "LocationName"
        ],
        "description": "A country name.",
        "fields": []
      },
      {
        "concept": "CurrencyCode",
        "parents": [
          "Entity"
        ],
        "description": "An ISO 4217 currency code.",
        "fields": []
      },
      {
        "concept": "DateTimeISO",
        "parents": [
          "Entity"
        ],
        "description": "An ISO 8601 date or timestamp.",
        "fields": []
      },
      {
        "concept": "DocumentQuestion",
        "parents": [
          "Entity"
        ],
        "description": "A question about an uploaded document.",
        "fields": []
      },
      {
        "concept": "DocumentReference",
        "parents": [
          "Entity"
        ],
        "description": "An identifier for an uploaded document.",
        "fields": []
      },
      {
        "concept": "Entity",
        "parents": [],
        "description": "Root of the upper ontology.",
        "fields": []
      },
      {
        "concept": "Evidence",
        "parents": [
          "Entity"
        ],
        "description": "Documentation or probe evidence.",
        "fields": []
      },
      {
        "concept": "Holiday",
        "parents": [
          "Entity"
        ],
        "description": "A public holiday.",
        "fields": [
          "date",
          "name",
          "local_name",
          "country_code"
        ]
      },
      {
        "concept": "LocationName",
        "parents": [
          "Entity"
        ],
        "description": "A place name supplied by a user.",
        "fields": []
      },
      {
        "concept": "Money",
        "parents": [
          "Entity"
        ],
        "description": "A monetary amount in a currency.",
        "fields": [
          "amount",
          "currency",
          "rate",
          "from",
          "to"
        ]
      },
      {
        "concept": "MoneyAmount",
        "parents": [
          "Number"
        ],
        "description": "A numeric amount of money.",
        "fields": []
      },
      {
        "concept": "NaturalLanguageQuery",
        "parents": [
          "Entity"
        ],
        "description": "A question over structured data.",
        "fields": []
      },
      {
        "concept": "Number",
        "parents": [
          "Entity"
        ],
        "description": "A numeric literal.",
        "fields": []
      },
      {
        "concept": "Provider",
        "parents": [
          "Entity"
        ],
        "description": "The party offering a service.",
        "fields": []
      },
      {
        "concept": "ResearchPaper",
        "parents": [
          "Entity"
        ],
        "description": "A research paper record.",
        "fields": [
          "title",
          "summary",
          "url",
          "published"
        ]
      },
      {
        "concept": "ResearchTopic",
        "parents": [
          "Entity"
        ],
        "description": "A research search topic.",
        "fields": []
      },
      {
        "concept": "Service",
        "parents": [
          "Entity"
        ],
        "description": "A callable third-party service.",
        "fields": []
      },
      {
        "concept": "TabularAnswer",
        "parents": [
          "Entity"
        ],
        "description": "Rows and columns returned by a database query.",
        "fields": [
          "columns",
          "rows",
          "sql",
          "row_count"
        ]
      },
      {
        "concept": "Temperature",
        "parents": [
          "Entity"
        ],
        "description": "An air temperature with a unit.",
        "fields": [
          "temperature",
          "temp_max",
          "temp_min",
          "unit"
        ]
      },
      {
        "concept": "Text",
        "parents": [
          "Entity"
        ],
        "description": "Plain text.",
        "fields": []
      }
    ],
    "units": [
      {
        "unit": "AED",
        "dimension": "currency",
        "convertible": [
          "USD",
          "PKR",
          "EUR",
          "GBP",
          "JPY",
          "INR"
        ]
      },
      {
        "unit": "C",
        "dimension": "temperature",
        "convertible": [
          "F",
          "K"
        ]
      },
      {
        "unit": "EUR",
        "dimension": "currency",
        "convertible": [
          "USD",
          "PKR",
          "GBP",
          "JPY",
          "INR",
          "AED"
        ]
      },
      {
        "unit": "F",
        "dimension": "temperature",
        "convertible": [
          "C",
          "K"
        ]
      },
      {
        "unit": "GBP",
        "dimension": "currency",
        "convertible": [
          "USD",
          "PKR",
          "EUR",
          "JPY",
          "INR",
          "AED"
        ]
      },
      {
        "unit": "INR",
        "dimension": "currency",
        "convertible": [
          "USD",
          "PKR",
          "EUR",
          "GBP",
          "JPY",
          "AED"
        ]
      },
      {
        "unit": "ISO8601",
        "dimension": "time",
        "convertible": []
      },
      {
        "unit": "JPY",
        "dimension": "currency",
        "convertible": [
          "USD",
          "PKR",
          "EUR",
          "GBP",
          "INR",
          "AED"
        ]
      },
      {
        "unit": "K",
        "dimension": "temperature",
        "convertible": [
          "C",
          "F"
        ]
      },
      {
        "unit": "PKR",
        "dimension": "currency",
        "convertible": [
          "USD",
          "EUR",
          "GBP",
          "JPY",
          "INR",
          "AED"
        ]
      },
      {
        "unit": "USD",
        "dimension": "currency",
        "convertible": [
          "PKR",
          "EUR",
          "GBP",
          "JPY",
          "INR",
          "AED"
        ]
      },
      {
        "unit": "degrees",
        "dimension": "angle",
        "convertible": []
      },
      {
        "unit": "year",
        "dimension": "time",
        "convertible": []
      }
    ],
    "capabilities": {
      "GeocodeLocation": {
        "description": "Resolve a place name to coordinates.",
        "inputs": [
          "LocationName"
        ],
        "outputs": [
          "Coordinates"
        ]
      },
      "GetWeatherForecast": {
        "description": "Return a weather forecast for coordinates.",
        "inputs": [
          "Coordinates"
        ],
        "outputs": [
          "Temperature"
        ]
      },
      "ConvertCurrency": {
        "description": "Convert an amount between currencies.",
        "inputs": [
          "MoneyAmount",
          "CurrencyCode"
        ],
        "outputs": [
          "Money"
        ]
      },
      "GetCountryFacts": {
        "description": "Return facts about a country.",
        "inputs": [
          "CountryName"
        ],
        "outputs": [
          "Country"
        ]
      },
      "GetPublicHolidays": {
        "description": "Return public holidays for a country and year.",
        "inputs": [
          "CountryCode",
          "Number"
        ],
        "outputs": [
          "Holiday"
        ]
      },
      "SearchResearchPapers": {
        "description": "Search scholarly papers by topic.",
        "inputs": [
          "ResearchTopic"
        ],
        "outputs": [
          "ResearchPaper"
        ]
      },
      "QueryStructuredData": {
        "description": "Answer a question using a read-only SQL database.",
        "inputs": [
          "NaturalLanguageQuery"
        ],
        "outputs": [
          "TabularAnswer"
        ]
      },
      "AnswerFromDocument": {
        "description": "Answer a question from an uploaded document.",
        "inputs": [
          "DocumentQuestion",
          "DocumentReference"
        ],
        "outputs": [
          "AnswerFromDocument"
        ]
      }
    }
  },
  "monitoring": {
    "trust": [
      {
        "provider_id": "arxiv",
        "successes": 1.5,
        "failures": 0.0,
        "score": 0.7143,
        "evidence": 1.5,
        "probes": 0,
        "calls": 1,
        "schema_pass": 1,
        "ratings_sum": 0.0,
        "ratings_count": 0,
        "contradictions": 0,
        "demoted": false,
        "updated_at": "2026-10-24T13:45:56.133203+00:00"
      },
      {
        "provider_id": "frankfurter",
        "successes": 1.5,
        "failures": 0.0,
        "score": 0.7143,
        "evidence": 1.5,
        "probes": 0,
        "calls": 1,
        "schema_pass": 1,
        "ratings_sum": 0.0,
        "ratings_count": 0,
        "contradictions": 0,
        "demoted": false,
        "updated_at": "2026-10-24T13:45:55.913610+00:00"
      },
      {
        "provider_id": "nager-date",
        "successes": 1.5,
        "failures": 0.0,
        "score": 0.7143,
        "evidence": 1.5,
        "probes": 0,
        "calls": 1,
        "schema_pass": 1,
        "ratings_sum": 0.0,
        "ratings_count": 0,
        "contradictions": 0,
        "demoted": false,
        "updated_at": "2026-10-24T13:45:56.056431+00:00"
      },
      {
        "provider_id": "nominatim",
        "successes": 1.5,
        "failures": 0.0,
        "score": 0.7143,
        "evidence": 1.5,
        "probes": 0,
        "calls": 1,
        "schema_pass": 1,
        "ratings_sum": 0.0,
        "ratings_count": 0,
        "contradictions": 0,
        "demoted": false,
        "updated_at": "2026-10-24T13:45:55.834567+00:00"
      },
      {
        "provider_id": "open-meteo",
        "successes": 0.0,
        "failures": 3.0,
        "score": 0.2,
        "evidence": 3.0,
        "probes": 0,
        "calls": 1,
        "schema_pass": 0,
        "ratings_sum": 0.0,
        "ratings_count": 0,
        "contradictions": 1,
        "demoted": true,
        "updated_at": "2026-10-24T13:45:56.151928+00:00"
      },
      {
        "provider_id": "open-meteo-backup",
        "successes": 1.5,
        "failures": 0.0,
        "score": 0.7143,
        "evidence": 1.5,
        "probes": 0,
        "calls": 1,
        "schema_pass": 1,
        "ratings_sum": 0.0,
        "ratings_count": 0,
        "contradictions": 0,
        "demoted": false,
        "updated_at": "2026-10-24T13:45:55.881872+00:00"
      },
      {
        "provider_id": "university-db",
        "successes": 1.5,
        "failures": 0.0,
        "score": 0.7143,
        "evidence": 1.5,
        "probes": 0,
        "calls": 1,
        "schema_pass": 1,
        "ratings_sum": 0.0,
        "ratings_count": 0,
        "contradictions": 0,
        "demoted": false,
        "updated_at": "2026-10-24T13:45:55.993103+00:00"
      }
    ],
    "breakers": [
      {
        "key": "client->arxiv",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->arxiv-backup",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->document-service",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->frankfurter",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->frankfurter-backup",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->mock-weather-fahrenheit",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->nager-date",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->nager-date-backup",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->nominatim",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->nominatim-backup",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->open-meteo",
        "state": "open",
        "consecutive_failures": 1,
        "opened_at": 1064.343,
        "last_error": "drift alert drift_b5e22958e813",
        "transitions": [
          {
            "at": 1064.343,
            "from": "closed",
            "to": "open",
            "reason": "drift alert drift_b5e22958e813"
          }
        ]
      },
      {
        "key": "client->open-meteo-backup",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->rest-countries",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->rest-countries-backup",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      },
      {
        "key": "client->university-db",
        "state": "closed",
        "consecutive_failures": 0,
        "opened_at": null,
        "last_error": "",
        "transitions": []
      }
    ],
    "drift_alerts": [
      {
        "message_id": "msg_21ce70df32cb",
        "timestamp": "2026-10-24T13:45:56.151928Z",
        "sender": "auditor",
        "recipient": "client",
        "correlation_id": "drift:open-meteo-forecast",
        "kind": "DriftAlert",
        "alert_id": "drift_b5e22958e813",
        "tool_id": "open-meteo-forecast",
        "provider_id": "open-meteo",
        "severity": "high",
        "reasons": [
          "Injected drift: response no longer matches the mapped schema."
        ],
        "detected_at": "2026-10-24T13:45:56.151928Z"
      }
    ],
    "providers": [
      {
        "provider_id": "arxiv",
        "tool_id": "arxiv-search",
        "tool_name": "arXiv Research Search",
        "capability": "SearchResearchPapers",
        "execution": "live",
        "trust": 0.7143,
        "demoted": false,
        "contradictions": 0,
        "calls": 1,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "arxiv-backup",
        "tool_id": "arxiv-search-backup",
        "tool_name": "arXiv Research Search (Backup Mirror)",
        "capability": "SearchResearchPapers",
        "execution": "mock",
        "trust": 0.5,
        "demoted": false,
        "contradictions": 0,
        "calls": 0,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "document-service",
        "tool_id": "document-qa",
        "tool_name": "Uploaded Document Question Answering",
        "capability": "AnswerFromDocument",
        "execution": "live",
        "trust": 0.5,
        "demoted": false,
        "contradictions": 0,
        "calls": 0,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "frankfurter",
        "tool_id": "frankfurter-currency",
        "tool_name": "Frankfurter Currency Converter",
        "capability": "ConvertCurrency",
        "execution": "live",
        "trust": 0.7143,
        "demoted": false,
        "contradictions": 0,
        "calls": 1,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "frankfurter-backup",
        "tool_id": "frankfurter-currency-backup",
        "tool_name": "Frankfurter Currency Converter (Backup Mirror)",
        "capability": "ConvertCurrency",
        "execution": "mock",
        "trust": 0.5,
        "demoted": false,
        "contradictions": 0,
        "calls": 0,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "mock-weather-fahrenheit",
        "tool_id": "mock-weather-fahrenheit",
        "tool_name": "Mock Weather Adversary",
        "capability": "GetWeatherForecast",
        "execution": "mock",
        "trust": 0.5,
        "demoted": false,
        "contradictions": 0,
        "calls": 0,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "nager-date",
        "tool_id": "nager-holidays",
        "tool_name": "Nager.Date Public Holidays",
        "capability": "GetPublicHolidays",
        "execution": "live",
        "trust": 0.7143,
        "demoted": false,
        "contradictions": 0,
        "calls": 1,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "nager-date-backup",
        "tool_id": "nager-holidays-backup",
        "tool_name": "Nager.Date Public Holidays (Backup Mirror)",
        "capability": "GetPublicHolidays",
        "execution": "mock",
        "trust": 0.5,
        "demoted": false,
        "contradictions": 0,
        "calls": 0,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "nominatim",
        "tool_id": "nominatim-geocode",
        "tool_name": "OpenStreetMap Nominatim Geocoder",
        "capability": "GeocodeLocation",
        "execution": "live",
        "trust": 0.7143,
        "demoted": false,
        "contradictions": 0,
        "calls": 1,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "nominatim-backup",
        "tool_id": "nominatim-geocode-backup",
        "tool_name": "OpenStreetMap Nominatim Geocoder (Backup Mirror)",
        "capability": "GeocodeLocation",
        "execution": "mock",
        "trust": 0.5,
        "demoted": false,
        "contradictions": 0,
        "calls": 0,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "open-meteo",
        "tool_id": "open-meteo-forecast",
        "tool_name": "Open-Meteo Weather Forecast",
        "capability": "GetWeatherForecast",
        "execution": "live",
        "trust": 0.2,
        "demoted": true,
        "contradictions": 1,
        "calls": 1,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "open-meteo-backup",
        "tool_id": "open-meteo-forecast-backup",
        "tool_name": "Open-Meteo Weather Forecast (Backup Mirror)",
        "capability": "GetWeatherForecast",
        "execution": "mock",
        "trust": 0.7143,
        "demoted": false,
        "contradictions": 0,
        "calls": 1,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "rest-countries",
        "tool_id": "restcountries-facts",
        "tool_name": "REST Countries Fact Service",
        "capability": "GetCountryFacts",
        "execution": "live",
        "trust": 0.5,
        "demoted": false,
        "contradictions": 0,
        "calls": 0,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "rest-countries-backup",
        "tool_id": "restcountries-facts-backup",
        "tool_name": "REST Countries Fact Service (Backup Mirror)",
        "capability": "GetCountryFacts",
        "execution": "mock",
        "trust": 0.5,
        "demoted": false,
        "contradictions": 0,
        "calls": 0,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      },
      {
        "provider_id": "university-db",
        "tool_id": "university-sql",
        "tool_name": "University Read-only SQL Provider",
        "capability": "QueryStructuredData",
        "execution": "live",
        "trust": 0.7143,
        "demoted": false,
        "contradictions": 0,
        "calls": 1,
        "probes": 0,
        "failure_mode": "offline",
        "fail_next": 0
      }
    ],
    "mode": "offline"
  },
  "recent": {
    "tasks": [
      {
        "task_id": "task_76de6fed3338",
        "task": "According to the uploaded document, what is the main goal of the project?",
        "status": "completed",
        "created_at": "2026-10-24T13:47:53.600470Z"
      },
      {
        "task_id": "task_773d82f5f573",
        "task": "Find recent research papers on GraphRAG.",
        "status": "completed",
        "created_at": "2026-10-24T13:45:56.136219+00:00"
      },
      {
        "task_id": "task_c71492081236",
        "task": "Which public holidays does Pakistan have in 2026?",
        "status": "completed",
        "created_at": "2026-10-24T13:45:56.073892+00:00"
      },
      {
        "task_id": "task_c93bb2c064ed",
        "task": "How many students are enrolled in the BS Artificial Intelligence program?",
        "status": "completed",
        "created_at": "2026-10-24T13:45:56.007064+00:00"
      },
      {
        "task_id": "task_2a4ef4f5c5b9",
        "task": "What is the temperature in Lahore tomorrow, and what is 200 USD in PKR?",
        "status": "completed",
        "created_at": "2026-10-24T13:45:55.929335+00:00"
      }
    ]
  },
  "tasks": [
    {
      "task_id": "task_2a4ef4f5c5b9",
      "task": "What is the temperature in Lahore tomorrow, and what is 200 USD in PKR?",
      "status": "completed",
      "answer": "Weather for Lahore on 2026-10-25: high 37.9 C, low 28.3 C, 6% chance of precipitation. 200.00 USD is approximately 55,700.00 PKR at rate 278.5 (2026-10-24). A provider failed during execution, so the Client recovered the chain with a type-compatible substitute behind the circuit breaker.",
      "subgoals": [
        {
          "id": "g1",
          "capability": "GeocodeLocation",
          "description": "Geocode the location Lahore to latitude and longitude.",
          "intent": "location lookup",
          "slots": {
            "location": "Lahore"
          },
          "depends_on": [],
          "branch": "weather"
        },
        {
          "id": "g2",
          "capability": "GetWeatherForecast",
          "description": "Weather forecast and temperature for Lahore on 2026-10-25.",
          "intent": "weather forecast",
          "slots": {
            "date": "2026-10-25",
            "location": "Lahore"
          },
          "depends_on": [
            "g1"
          ],
          "branch": "weather"
        },
        {
          "id": "g3",
          "capability": "ConvertCurrency",
          "description": "Convert 200 USD to PKR using the current exchange rate.",
          "intent": "currency conversion",
          "slots": {
            "amount": 200.0,
            "from_currency": "USD",
            "to_currency": "PKR"
          },
          "depends_on": [],
          "branch": "currency"
        }
      ],
      "candidate_lists": [
        {
          "message_id": "msg_8761d9af266f",
          "timestamp": "2026-10-24T13:45:55.788885Z",
          "sender": "client",
          "recipient": "interface",
          "correlation_id": "task_2a4ef4f5c5b9",
          "kind": "CandidateList",
          "task_id": "task_2a4ef4f5c5b9",
          "subgoal_id": "g1",
          "capability": "GeocodeLocation",
          "candidates": [
            {
              "tool": {
                "id": "nominatim-geocode",
                "name": "OpenStreetMap Nominatim Geocoder",
                "provider_id": "nominatim",
                "description": "Resolve a city or place name to latitude, longitude and a display name using the public OpenStreetMap Nominatim search API.",
                "capability": "GeocodeLocation",
                "inputs": [
                  {
                    "concept": "LocationName",
                    "name": "location",
                    "unit": null,
                    "datatype": "string",
                    "required": true,
                    "description": "City, address or place name to resolve.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "Coordinates",
                    "name": "coordinates",
                    "unit": "degrees",
                    "datatype": "object",
                    "required": true,
                    "description": "WGS84 coordinates for the resolved place.",
                    "fields": [
                      "latitude",
                      "longitude",
                      "display_name",
                      "country_code"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Resolves place names without an API key.",
                    "label": "Verified",
                    "evidence": "Seeded demo evidence from the public Nominatim endpoint; the live Auditor replaces this.",
                    "checked_at": null
                  },
                  {
                    "text": "Returns coordinates in WGS84 degrees.",
                    "label": "Supported",
                    "evidence": "Nominatim API documentation.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "geocode",
                  "geocoding",
                  "location",
                  "city",
                  "place",
                  "map",
                  "coordinates",
                  "latitude",
                  "longitude",
                  "address"
                ],
                "docs_url": "https://nominatim.org/release-docs/latest/api/Search/",
                "price": 0.0,
                "probe_eligible": true,
                "execution": "live",
                "tags": [
                  "api",
                  "geospatial",
                  "backup-eligible"
                ]
              },
              "relevance": 1.0,
              "trust": 0.5,
              "score": 0.5,
              "rank": 1,
              "reasons": [
                "lexical similarity 0.35",
                "capability GeocodeLocation matched",
                "typed inputs fit the sub-goal",
                "trust 0.50",
                "claim label Verified"
              ],
              "claim_label": "Verified",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            },
            {
              "tool": {
                "id": "nominatim-geocode-backup",
                "name": "OpenStreetMap Nominatim Geocoder (Backup Mirror)",
                "provider_id": "nominatim-backup",
                "description": "Standby backup mirror used to test circuit-breaker substitution. Mirrors OpenStreetMap Nominatim Geocoder. Resolve a city or place name to latitude, longitude and a display name using the public OpenStreetMap Nominatim search API.",
                "capability": "GeocodeLocation",
                "inputs": [
                  {
                    "concept": "LocationName",
                    "name": "location",
                    "unit": null,
                    "datatype": "string",
                    "required": true,
                    "description": "City, address or place name to resolve.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "Coordinates",
                    "name": "coordinates",
                    "unit": "degrees",
                    "datatype": "object",
                    "required": true,
                    "description": "WGS84 coordinates for the resolved place.",
                    "fields": [
                      "latitude",
                      "longitude",
                      "display_name",
                      "country_code"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Resolves place names without an API key.",
                    "label": "Unsupported",
                    "evidence": "Backup mirror; not independently verified.",
                    "checked_at": null
                  },
                  {
                    "text": "Returns coordinates in WGS84 degrees.",
                    "label": "Unsupported",
                    "evidence": "Backup mirror; not independently verified.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "geocode",
                  "geocoding",
                  "location",
                  "city",
                  "place",
                  "map",
                  "coordinates",
                  "latitude",
                  "longitude",
                  "address"
                ],
                "docs_url": "https://nominatim.org/release-docs/latest/api/Search/",
                "price": 0.0,
                "probe_eligible": false,
                "execution": "mock",
                "tags": [
                  "api",
                  "geospatial",
                  "backup-eligible",
                  "backup"
                ]
              },
              "relevance": 0.9055,
              "trust": 0.5,
              "score": 0.4527,
              "rank": 2,
              "reasons": [
                "lexical similarity 0.32",
                "capability GeocodeLocation matched",
                "typed inputs fit the sub-goal",
                "trust 0.50",
                "claim label Unsupported"
              ],
              "claim_label": "Unsupported",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            }
          ]
        },
        {
          "message_id": "msg_225565ec4954",
          "timestamp": "2026-10-24T13:45:55.804469Z",
          "sender": "client",
          "recipient": "interface",
          "correlation_id": "task_2a4ef4f5c5b9",
          "kind": "CandidateList",
          "task_id": "task_2a4ef4f5c5b9",
          "subgoal_id": "g2",
          "capability": "GetWeatherForecast",
          "candidates": [
            {
              "tool": {
                "id": "open-meteo-forecast",
                "name": "Open-Meteo Weather Forecast",
                "provider_id": "open-meteo",
                "description": "Return a daily weather forecast with maximum and minimum temperature, rain probability and timezone for a coordinate pair.",
                "capability": "GetWeatherForecast",
                "inputs": [
                  {
                    "concept": "Coordinates",
                    "name": "coordinates",
                    "unit": "degrees",
                    "datatype": "object",
                    "required": true,
                    "description": "Latitude and longitude from a geocoder.",
                    "fields": []
                  },
                  {
                    "concept": "DateTimeISO",
                    "name": "date",
                    "unit": null,
                    "datatype": "string",
                    "required": false,
                    "description": "ISO date to forecast; tomorrow by default.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "Temperature",
                    "name": "forecast",
                    "unit": "C",
                    "datatype": "object",
                    "required": true,
                    "description": "Daily forecast values in degrees Celsius.",
                    "fields": [
                      "temperature",
                      "temp_max",
                      "temp_min",
                      "precipitation_probability",
                      "date",
                      "timezone"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Returns temperatures in Celsius.",
                    "label": "Verified",
                    "evidence": "Seeded demo evidence from the public forecast endpoint; the live Auditor replaces this.",
                    "checked_at": null
                  },
                  {
                    "text": "No API key is required.",
                    "label": "Verified",
                    "evidence": "Open-Meteo free endpoint documentation.",
                    "checked_at": null
                  },
                  {
                    "text": "Provides a daily forecast for the requested location.",
                    "label": "Supported",
                    "evidence": "Open-Meteo forecast API documentation.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "weather",
                  "temperature",
                  "forecast",
                  "rain",
                  "precipitation",
                  "tomorrow",
                  "celsius",
                  "hot",
                  "cold",
                  "climate"
                ],
                "docs_url": "https://open-meteo.com/en/docs",
                "price": 0.0,
                "probe_eligible": true,
                "execution": "live",
                "tags": [
                  "api",
                  "weather",
                  "backup-eligible"
                ]
              },
              "relevance": 1.0,
              "trust": 0.5,
              "score": 0.5,
              "rank": 1,
              "reasons": [
                "lexical similarity 0.34",
                "capability GetWeatherForecast matched",
                "typed inputs fit the sub-goal",
                "trust 0.50",
                "claim label Verified"
              ],
              "claim_label": "Verified",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            },
            {
              "tool": {
                "id": "open-meteo-forecast-backup",
                "name": "Open-Meteo Weather Forecast (Backup Mirror)",
                "provider_id": "open-meteo-backup",
                "description": "Standby backup mirror used to test circuit-breaker substitution. Mirrors Open-Meteo Weather Forecast. Return a daily weather forecast with maximum and minimum temperature, rain probability and timezone for a coordinate pair.",
                "capability": "GetWeatherForecast",
                "inputs": [
                  {
                    "concept": "Coordinates",
                    "name": "coordinates",
                    "unit": "degrees",
                    "datatype": "object",
                    "required": true,
                    "description": "Latitude and longitude from a geocoder.",
                    "fields": []
                  },
                  {
                    "concept": "DateTimeISO",
                    "name": "date",
                    "unit": null,
                    "datatype": "string",
                    "required": false,
                    "description": "ISO date to forecast; tomorrow by default.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "Temperature",
                    "name": "forecast",
                    "unit": "C",
                    "datatype": "object",
                    "required": true,
                    "description": "Daily forecast values in degrees Celsius.",
                    "fields": [
                      "temperature",
                      "temp_max",
                      "temp_min",
                      "precipitation_probability",
                      "date",
                      "timezone"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Returns temperatures in Celsius.",
                    "label": "Unsupported",
                    "evidence": "Backup mirror; not independently verified.",
                    "checked_at": null
                  },
                  {
                    "text": "No API key is required.",
                    "label": "Unsupported",
                    "evidence": "Backup mirror; not independently verified.",
                    "checked_at": null
                  },
                  {
                    "text": "Provides a daily forecast for the requested location.",
                    "label": "Unsupported",
                    "evidence": "Backup mirror; not independently verified.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "weather",
                  "temperature",
                  "forecast",
                  "rain",
                  "precipitation",
                  "tomorrow",
                  "celsius",
                  "hot",
                  "cold",
                  "climate"
                ],
                "docs_url": "https://open-meteo.com/en/docs",
                "price": 0.0,
                "probe_eligible": false,
                "execution": "mock",
                "tags": [
                  "api",
                  "weather",
                  "backup-eligible",
                  "backup"
                ]
              },
              "relevance": 0.9472,
              "trust": 0.5,
              "score": 0.4736,
              "rank": 2,
              "reasons": [
                "lexical similarity 0.32",
                "capability GetWeatherForecast matched",
                "typed inputs fit the sub-goal",
                "trust 0.50",
                "claim label Unsupported"
              ],
              "claim_label": "Unsupported",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            },
            {
              "tool": {
                "id": "mock-weather-fahrenheit",
                "name": "Mock Weather Adversary",
                "provider_id": "mock-weather-fahrenheit",
                "description": "A deliberately misleading weather tool that claims Celsius but returns Fahrenheit values, used to test claim badges and unit checks.",
                "capability": "GetWeatherForecast",
                "inputs": [
                  {
                    "concept": "Coordinates",
                    "name": "coordinates",
                    "unit": "degrees",
                    "datatype": "object",
                    "required": true,
                    "description": "Latitude and longitude.",
                    "fields": []
                  },
                  {
                    "concept": "DateTimeISO",
                    "name": "date",
                    "unit": null,
                    "datatype": "string",
                    "required": false,
                    "description": "ISO date.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "Temperature",
                    "name": "forecast",
                    "unit": "F",
                    "datatype": "object",
                    "required": true,
                    "description": "Forecast values in Fahrenheit despite the Celsius claim.",
                    "fields": [
                      "temperature",
                      "temp_max",
                      "temp_min",
                      "unit"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Returns temperature in Celsius.",
                    "label": "Contradicted",
                    "evidence": "Seeded adversarial provider: the payload unit is Fahrenheit.",
                    "checked_at": null
                  },
                  {
                    "text": "No API key is required.",
                    "label": "Verified",
                    "evidence": "Mock provider is local.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "weather",
                  "temperature",
                  "mock",
                  "fahrenheit",
                  "unreliable",
                  "forecast"
                ],
                "docs_url": "",
                "price": 0.0,
                "probe_eligible": true,
                "execution": "mock",
                "tags": [
                  "mock",
                  "adversarial",
                  "weather"
                ]
              },
              "relevance": 0.8593,
              "trust": 0.5,
              "score": 0.2578,
              "rank": 3,
              "reasons": [
                "lexical similarity 0.29",
                "capability GetWeatherForecast matched",
                "typed inputs fit the sub-goal",
                "contradicted claim penalty applied",
                "trust 0.50",
                "claim label Contradicted"
              ],
              "claim_label": "Contradicted",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            }
          ]
        },
        {
          "message_id": "msg_184f63cd190f",
          "timestamp": "2026-10-24T13:45:55.820520Z",
          "sender": "client",
          "recipient": "interface",
          "correlation_id": "task_2a4ef4f5c5b9",
          "kind": "CandidateList",
          "task_id": "task_2a4ef4f5c5b9",
          "subgoal_id": "g3",
          "capability": "ConvertCurrency",
          "candidates": [
            {
              "tool": {
                "id": "frankfurter-currency",
                "name": "Frankfurter Currency Converter",
                "provider_id": "frankfurter",
                "description": "Convert a monetary amount between currencies using keyless reference exchange rates.",
                "capability": "ConvertCurrency",
                "inputs": [
                  {
                    "concept": "MoneyAmount",
                    "name": "amount",
                    "unit": null,
                    "datatype": "number",
                    "required": true,
                    "description": "Amount to convert.",
                    "fields": []
                  },
                  {
                    "concept": "CurrencyCode",
                    "name": "from_currency",
                    "unit": null,
                    "datatype": "string",
                    "required": true,
                    "description": "ISO 4217 source currency code.",
                    "fields": []
                  },
                  {
                    "concept": "CurrencyCode",
                    "name": "to_currency",
                    "unit": null,
                    "datatype": "string",
                    "required": true,
                    "description": "ISO 4217 target currency code.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "Money",
                    "name": "conversion",
                    "unit": null,
                    "datatype": "object",
                    "required": true,
                    "description": "Converted amount and exchange rate.",
                    "fields": [
                      "amount",
                      "currency",
                      "rate",
                      "from",
                      "to",
                      "date"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Converts an amount between supported currencies without an API key.",
                    "label": "Supported",
                    "evidence": "Frankfurter documentation; PKR is served by the documented keyless fallback.",
                    "checked_at": null
                  },
                  {
                    "text": "The output states the effective rate and date.",
                    "label": "Supported",
                    "evidence": "Provider response schema.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "currency",
                  "exchange",
                  "rate",
                  "convert",
                  "money",
                  "usd",
                  "pkr",
                  "eur",
                  "dollar",
                  "rupee",
                  "conversion"
                ],
                "docs_url": "https://www.frankfurter.app/docs/",
                "price": 0.0,
                "probe_eligible": true,
                "execution": "live",
                "tags": [
                  "api",
                  "finance",
                  "backup-eligible"
                ]
              },
              "relevance": 1.0,
              "trust": 0.5,
              "score": 0.5,
              "rank": 1,
              "reasons": [
                "lexical similarity 0.44",
                "capability ConvertCurrency matched",
                "typed inputs fit the sub-goal",
                "trust 0.50",
                "claim label Supported"
              ],
              "claim_label": "Supported",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            },
            {
              "tool": {
                "id": "frankfurter-currency-backup",
                "name": "Frankfurter Currency Converter (Backup Mirror)",
                "provider_id": "frankfurter-backup",
                "description": "Standby backup mirror used to test circuit-breaker substitution. Mirrors Frankfurter Currency Converter. Convert a monetary amount between currencies using keyless reference exchange rates.",
                "capability": "ConvertCurrency",
                "inputs": [
                  {
                    "concept": "MoneyAmount",
                    "name": "amount",
                    "unit": null,
                    "datatype": "number",
                    "required": true,
                    "description": "Amount to convert.",
                    "fields": []
                  },
                  {
                    "concept": "CurrencyCode",
                    "name": "from_currency",
                    "unit": null,
                    "datatype": "string",
                    "required": true,
                    "description": "ISO 4217 source currency code.",
                    "fields": []
                  },
                  {
                    "concept": "CurrencyCode",
                    "name": "to_currency",
                    "unit": null,
                    "datatype": "string",
                    "required": true,
                    "description": "ISO 4217 target currency code.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "Money",
                    "name": "conversion",
                    "unit": null,
                    "datatype": "object",
                    "required": true,
                    "description": "Converted amount and exchange rate.",
                    "fields": [
                      "amount",
                      "currency",
                      "rate",
                      "from",
                      "to",
                      "date"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Converts an amount between supported currencies without an API key.",
                    "label": "Unsupported",
                    "evidence": "Backup mirror; not independently verified.",
                    "checked_at": null
                  },
                  {
                    "text": "The output states the effective rate and date.",
                    "label": "Unsupported",
                    "evidence": "Backup mirror; not independently verified.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "currency",
                  "exchange",
                  "rate",
                  "convert",
                  "money",
                  "usd",
                  "pkr",
                  "eur",
                  "dollar",
                  "rupee",
                  "conversion"
                ],
                "docs_url": "https://www.frankfurter.app/docs/",
                "price": 0.0,
                "probe_eligible": false,
                "execution": "mock",
                "tags": [
                  "api",
                  "finance",
                  "backup-eligible",
                  "backup"
                ]
              },
              "relevance": 0.9182,
              "trust": 0.5,
              "score": 0.4591,
              "rank": 2,
              "reasons": [
                "lexical similarity 0.40",
                "capability ConvertCurrency matched",
                "typed inputs fit the sub-goal",
                "trust 0.50",
                "claim label Unsupported"
              ],
              "claim_label": "Unsupported",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            }
          ]
        }
      ],
      "plan": {
        "plan_id": "plan_294ed9639472",
        "task_id": "task_2a4ef4f5c5b9",
        "steps": [
          {
            "id": "g1",
            "subgoal_id": "g1",
            "tool_id": "nominatim-geocode",
            "tool_name": "OpenStreetMap Nominatim Geocoder",
            "capability": "GeocodeLocation",
            "branch": "weather",
            "input_bindings": {
              "location": "$task.location"
            },
            "params": {
              "location": "Lahore"
            },
            "link_checks": [],
            "status": "completed",
            "output": {
              "coordinates": {
                "latitude": 31.5497,
                "longitude": 74.3436,
                "display_name": "Lahore, Punjab, Pakistan",
                "country_code": "PK"
              }
            },
            "error": null,
            "latency_ms": 2.94,
            "cached": false,
            "source": "fixture",
            "substituted_from": null
          },
          {
            "id": "g2",
            "subgoal_id": "g2",
            "tool_id": "open-meteo-forecast-backup",
            "tool_name": "Open-Meteo Weather Forecast (Backup Mirror)",
            "capability": "GetWeatherForecast",
            "branch": "weather",
            "input_bindings": {
              "coordinates": "$g1.coordinates",
              "date": "$task.date"
            },
            "params": {
              "coordinates": {
                "latitude": 31.5497,
                "longitude": 74.3436,
                "display_name": "Lahore, Punjab, Pakistan",
                "country_code": "PK"
              },
              "date": "2026-10-25"
            },
            "link_checks": [
              {
                "source_step": "g1",
                "target_step": "g2",
                "source_concept": "Coordinates",
                "target_concept": "Coordinates",
                "source_unit": "degrees",
                "target_unit": "degrees",
                "concept_ok": true,
                "units_ok": true,
                "valid": true,
                "reason": "Compatible: Coordinates matches Coordinates."
              }
            ],
            "status": "substituted",
            "output": {
              "forecast": {
                "temperature": 37.9,
                "temp_max": 37.9,
                "temp_min": 28.3,
                "precipitation_probability": 6,
                "date": "2026-10-25",
                "timezone": "Asia/Karachi",
                "location": "Lahore",
                "unit": "C"
              }
            },
            "error": null,
            "latency_ms": 1.18,
            "cached": false,
            "source": "fixture",
            "substituted_from": "open-meteo-forecast"
          },
          {
            "id": "g3",
            "subgoal_id": "g3",
            "tool_id": "frankfurter-currency",
            "tool_name": "Frankfurter Currency Converter",
            "capability": "ConvertCurrency",
            "branch": "currency",
            "input_bindings": {
              "amount": "$task.amount",
              "from_currency": "$task.from_currency",
              "to_currency": "$task.to_currency"
            },
            "params": {
              "amount": 200.0,
              "from_currency": "USD",
              "to_currency": "PKR"
            },
            "link_checks": [],
            "status": "completed",
            "output": {
              "conversion": {
                "amount": 55700.0,
                "currency": "PKR",
                "rate": 278.5,
                "from": "USD",
                "to": "PKR",
                "date": "2026-10-24",
                "source": "offline fixture"
              }
            },
            "error": null,
            "latency_ms": 2.96,
            "cached": false,
            "source": "fixture",
            "substituted_from": null
          }
        ],
        "branches": {
          "weather": [
            "g1",
            "g2"
          ],
          "currency": [
            "g3"
          ]
        },
        "valid": true,
        "errors": [],
        "created_at": "2026-10-24T13:45:55.820520Z"
      },
      "trace": [
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 1,
          "timestamp": "2026-10-24T13:45:55.763733Z",
          "event_type": "task_started",
          "actor": "client",
          "summary": "Task received by the Client agent.",
          "data": {
            "task": "What is the temperature in Lahore tomorrow, and what is 200 USD in PKR?",
            "mode": "offline"
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 2,
          "timestamp": "2026-10-24T13:45:55.770953Z",
          "event_type": "task_decomposed",
          "actor": "client",
          "summary": "Task decomposed into 3 sub-goal(s).",
          "data": {
            "subgoals": [
              {
                "id": "g1",
                "capability": "GeocodeLocation",
                "description": "Geocode the location Lahore to latitude and longitude.",
                "intent": "location lookup",
                "slots": {
                  "location": "Lahore"
                },
                "depends_on": [],
                "branch": "weather"
              },
              {
                "id": "g2",
                "capability": "GetWeatherForecast",
                "description": "Weather forecast and temperature for Lahore on 2026-10-25.",
                "intent": "weather forecast",
                "slots": {
                  "date": "2026-10-25",
                  "location": "Lahore"
                },
                "depends_on": [
                  "g1"
                ],
                "branch": "weather"
              },
              {
                "id": "g3",
                "capability": "ConvertCurrency",
                "description": "Convert 200 USD to PKR using the current exchange rate.",
                "intent": "currency conversion",
                "slots": {
                  "amount": 200.0,
                  "from_currency": "USD",
                  "to_currency": "PKR"
                },
                "depends_on": [],
                "branch": "currency"
              }
            ]
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 3,
          "timestamp": "2026-10-24T13:45:55.770953Z",
          "event_type": "graphrag_shortlist",
          "actor": "client",
          "summary": "Retrieved 2 candidate(s) for GeocodeLocation; 2 survived the filter.",
          "data": {
            "subgoal_id": "g1",
            "query": "Geocode the location Lahore to latitude and longitude. Lahore",
            "retrieved": [
              {
                "tool_id": "nominatim-geocode",
                "relevance": 1.0,
                "reasons": [
                  "lexical similarity 0.35"
                ]
              },
              {
                "tool_id": "nominatim-geocode-backup",
                "relevance": 0.9055,
                "reasons": [
                  "lexical similarity 0.32"
                ]
              }
            ],
            "filtered": []
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 4,
          "timestamp": "2026-10-24T13:45:55.782448Z",
          "event_type": "claims_verified",
          "actor": "auditor",
          "summary": "Claim labels returned for the candidate list.",
          "data": {
            "subgoal_id": "g1",
            "overall": {
              "nominatim-geocode": "Verified",
              "nominatim-geocode-backup": "Unsupported"
            }
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 5,
          "timestamp": "2026-10-24T13:45:55.790897Z",
          "event_type": "candidate_ranking",
          "actor": "client",
          "summary": "Ranked 2 candidate(s) for GeocodeLocation.",
          "data": {
            "subgoal_id": "g1",
            "ranked": [
              {
                "tool_id": "nominatim-geocode",
                "name": "OpenStreetMap Nominatim Geocoder",
                "score": 0.5,
                "relevance": 1.0,
                "trust": 0.5,
                "claim_label": "Verified",
                "eligible": true,
                "breaker": "closed"
              },
              {
                "tool_id": "nominatim-geocode-backup",
                "name": "OpenStreetMap Nominatim Geocoder (Backup Mirror)",
                "score": 0.4527,
                "relevance": 0.9055,
                "trust": 0.5,
                "claim_label": "Unsupported",
                "eligible": true,
                "breaker": "closed"
              }
            ]
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 6,
          "timestamp": "2026-10-24T13:45:55.790897Z",
          "event_type": "graphrag_shortlist",
          "actor": "client",
          "summary": "Retrieved 3 candidate(s) for GetWeatherForecast; 3 survived the filter.",
          "data": {
            "subgoal_id": "g2",
            "query": "Weather forecast and temperature for Lahore on 2026-10-25. 2026-10-25 Lahore",
            "retrieved": [
              {
                "tool_id": "open-meteo-forecast",
                "relevance": 1.0,
                "reasons": [
                  "lexical similarity 0.34"
                ]
              },
              {
                "tool_id": "open-meteo-forecast-backup",
                "relevance": 0.9472,
                "reasons": [
                  "lexical similarity 0.32"
                ]
              },
              {
                "tool_id": "mock-weather-fahrenheit",
                "relevance": 0.8593,
                "reasons": [
                  "lexical similarity 0.29"
                ]
              }
            ],
            "filtered": []
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 7,
          "timestamp": "2026-10-24T13:45:55.804469Z",
          "event_type": "claims_verified",
          "actor": "auditor",
          "summary": "Claim labels returned for the candidate list.",
          "data": {
            "subgoal_id": "g2",
            "overall": {
              "open-meteo-forecast": "Verified",
              "open-meteo-forecast-backup": "Unsupported",
              "mock-weather-fahrenheit": "Contradicted"
            }
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 8,
          "timestamp": "2026-10-24T13:45:55.804469Z",
          "event_type": "candidate_ranking",
          "actor": "client",
          "summary": "Ranked 3 candidate(s) for GetWeatherForecast.",
          "data": {
            "subgoal_id": "g2",
            "ranked": [
              {
                "tool_id": "open-meteo-forecast",
                "name": "Open-Meteo Weather Forecast",
                "score": 0.5,
                "relevance": 1.0,
                "trust": 0.5,
                "claim_label": "Verified",
                "eligible": true,
                "breaker": "closed"
              },
              {
                "tool_id": "open-meteo-forecast-backup",
                "name": "Open-Meteo Weather Forecast (Backup Mirror)",
                "score": 0.4736,
                "relevance": 0.9472,
                "trust": 0.5,
                "claim_label": "Unsupported",
                "eligible": true,
                "breaker": "closed"
              },
              {
                "tool_id": "mock-weather-fahrenheit",
                "name": "Mock Weather Adversary",
                "score": 0.2578,
                "relevance": 0.8593,
                "trust": 0.5,
                "claim_label": "Contradicted",
                "eligible": true,
                "breaker": "closed"
              }
            ]
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 9,
          "timestamp": "2026-10-24T13:45:55.804469Z",
          "event_type": "graphrag_shortlist",
          "actor": "client",
          "summary": "Retrieved 2 candidate(s) for ConvertCurrency; 2 survived the filter.",
          "data": {
            "subgoal_id": "g3",
            "query": "Convert 200 USD to PKR using the current exchange rate. 200.0 USD PKR",
            "retrieved": [
              {
                "tool_id": "frankfurter-currency",
                "relevance": 1.0,
                "reasons": [
                  "lexical similarity 0.44"
                ]
              },
              {
                "tool_id": "frankfurter-currency-backup",
                "relevance": 0.9182,
                "reasons": [
                  "lexical similarity 0.40"
                ]
              }
            ],
            "filtered": []
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 10,
          "timestamp": "2026-10-24T13:45:55.818515Z",
          "event_type": "claims_verified",
          "actor": "auditor",
          "summary": "Claim labels returned for the candidate list.",
          "data": {
            "subgoal_id": "g3",
            "overall": {
              "frankfurter-currency": "Supported",
              "frankfurter-currency-backup": "Unsupported"
            }
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 11,
          "timestamp": "2026-10-24T13:45:55.820520Z",
          "event_type": "candidate_ranking",
          "actor": "client",
          "summary": "Ranked 2 candidate(s) for ConvertCurrency.",
          "data": {
            "subgoal_id": "g3",
            "ranked": [
              {
                "tool_id": "frankfurter-currency",
                "name": "Frankfurter Currency Converter",
                "score": 0.5,
                "relevance": 1.0,
                "trust": 0.5,
                "claim_label": "Supported",
                "eligible": true,
                "breaker": "closed"
              },
              {
                "tool_id": "frankfurter-currency-backup",
                "name": "Frankfurter Currency Converter (Backup Mirror)",
                "score": 0.4591,
                "relevance": 0.9182,
                "trust": 0.5,
                "claim_label": "Unsupported",
                "eligible": true,
                "breaker": "closed"
              }
            ]
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 12,
          "timestamp": "2026-10-24T13:45:55.820520Z",
          "event_type": "planning_finished",
          "actor": "client",
          "summary": "Task decomposition and candidate matching finished.",
          "data": {
            "elapsed_ms": 55.14
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 13,
          "timestamp": "2026-10-24T13:45:55.820520Z",
          "event_type": "chain_composed",
          "actor": "client",
          "summary": "A valid execution chain was composed.",
          "data": {
            "valid": true,
            "steps": [
              {
                "id": "g1",
                "subgoal_id": "g1",
                "tool_id": "nominatim-geocode",
                "tool_name": "OpenStreetMap Nominatim Geocoder",
                "capability": "GeocodeLocation",
                "branch": "weather",
                "input_bindings": {
                  "location": "$task.location"
                },
                "params": {},
                "link_checks": [],
                "status": "pending",
                "output": null,
                "error": null,
                "latency_ms": 0.0,
                "cached": false,
                "source": "",
                "substituted_from": null
              },
              {
                "id": "g2",
                "subgoal_id": "g2",
                "tool_id": "open-meteo-forecast",
                "tool_name": "Open-Meteo Weather Forecast",
                "capability": "GetWeatherForecast",
                "branch": "weather",
                "input_bindings": {
                  "coordinates": "$g1.coordinates",
                  "date": "$task.date"
                },
                "params": {},
                "link_checks": [
                  {
                    "source_step": "g1",
                    "target_step": "g2",
                    "source_concept": "Coordinates",
                    "target_concept": "Coordinates",
                    "source_unit": "degrees",
                    "target_unit": "degrees",
                    "concept_ok": true,
                    "units_ok": true,
                    "valid": true,
                    "reason": "Compatible: Coordinates matches Coordinates."
                  }
                ],
                "status": "pending",
                "output": null,
                "error": null,
                "latency_ms": 0.0,
                "cached": false,
                "source": "",
                "substituted_from": null
              },
              {
                "id": "g3",
                "subgoal_id": "g3",
                "tool_id": "frankfurter-currency",
                "tool_name": "Frankfurter Currency Converter",
                "capability": "ConvertCurrency",
                "branch": "currency",
                "input_bindings": {
                  "amount": "$task.amount",
                  "from_currency": "$task.from_currency",
                  "to_currency": "$task.to_currency"
                },
                "params": {},
                "link_checks": [],
                "status": "pending",
                "output": null,
                "error": null,
                "latency_ms": 0.0,
                "cached": false,
                "source": "",
                "substituted_from": null
              }
            ],
            "errors": []
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 14,
          "timestamp": "2026-10-24T13:45:55.820520Z",
          "event_type": "step_started",
          "actor": "client",
          "summary": "Calling OpenStreetMap Nominatim Geocoder for GeocodeLocation.",
          "data": {
            "step_id": "g1",
            "tool_id": "nominatim-geocode",
            "params": {
              "location": "Lahore"
            },
            "input_bindings": {
              "location": "$task.location"
            }
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 15,
          "timestamp": "2026-10-24T13:45:55.850255Z",
          "event_type": "step_succeeded",
          "actor": "provider",
          "summary": "OpenStreetMap Nominatim Geocoder returned a schema-valid result.",
          "data": {
            "step_id": "g1",
            "tool_id": "nominatim-geocode",
            "status": "completed",
            "source": "fixture",
            "cached": false,
            "latency_ms": 2.94,
            "output": {
              "coordinates": {
                "latitude": 31.5497,
                "longitude": 74.3436,
                "display_name": "Lahore, Punjab, Pakistan",
                "country_code": "PK"
              }
            },
            "substituted_from": null
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 16,
          "timestamp": "2026-10-24T13:45:55.850255Z",
          "event_type": "step_started",
          "actor": "client",
          "summary": "Calling Open-Meteo Weather Forecast for GetWeatherForecast.",
          "data": {
            "step_id": "g2",
            "tool_id": "open-meteo-forecast",
            "params": {
              "coordinates": {
                "latitude": 31.5497,
                "longitude": 74.3436,
                "display_name": "Lahore, Punjab, Pakistan",
                "country_code": "PK"
              },
              "date": "2026-10-25"
            },
            "input_bindings": {
              "coordinates": "$g1.coordinates",
              "date": "$task.date"
            }
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 17,
          "timestamp": "2026-10-24T13:45:55.850255Z",
          "event_type": "step_failed",
          "actor": "provider",
          "summary": "Open-Meteo Weather Forecast failed: Injected provider outage for the demonstration.",
          "data": {
            "step_id": "g2",
            "tool_id": "open-meteo-forecast",
            "reason": "Injected provider outage for the demonstration.",
            "source": "mock"
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 18,
          "timestamp": "2026-10-24T13:45:55.865970Z",
          "event_type": "substitution_requested",
          "actor": "client",
          "summary": "Looking for a compatible substitute for open-meteo-forecast.",
          "data": {
            "step_id": "g2",
            "failed_tool": "open-meteo-forecast",
            "reason": "Injected provider outage for the demonstration.",
            "candidates": [
              "open-meteo-forecast-backup"
            ]
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 19,
          "timestamp": "2026-10-24T13:45:55.872750Z",
          "event_type": "substitute_selected",
          "actor": "client",
          "summary": "Substituting Open-Meteo Weather Forecast (Backup Mirror) for open-meteo-forecast.",
          "data": {
            "step_id": "g2",
            "tool_id": "open-meteo-forecast-backup",
            "failed_tool": "open-meteo-forecast",
            "params": {
              "coordinates": {
                "latitude": 31.5497,
                "longitude": 74.3436,
                "display_name": "Lahore, Punjab, Pakistan",
                "country_code": "PK"
              },
              "date": "2026-10-25"
            }
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 20,
          "timestamp": "2026-10-24T13:45:55.881872Z",
          "event_type": "step_succeeded",
          "actor": "provider",
          "summary": "Open-Meteo Weather Forecast (Backup Mirror) returned a schema-valid result.",
          "data": {
            "step_id": "g2",
            "tool_id": "open-meteo-forecast-backup",
            "status": "substituted",
            "source": "fixture",
            "cached": false,
            "latency_ms": 1.18,
            "output": {
              "forecast": {
                "temperature": 37.9,
                "temp_max": 37.9,
                "temp_min": 28.3,
                "precipitation_probability": 6,
                "date": "2026-10-25",
                "timezone": "Asia/Karachi",
                "location": "Lahore",
                "unit": "C"
              }
            },
            "substituted_from": "open-meteo-forecast"
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 21,
          "timestamp": "2026-10-24T13:45:55.897870Z",
          "event_type": "substitution_succeeded",
          "actor": "client",
          "summary": "Chain recovered with substitute open-meteo-forecast-backup.",
          "data": {
            "step_id": "g2",
            "tool_id": "open-meteo-forecast-backup"
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 22,
          "timestamp": "2026-10-24T13:45:55.898866Z",
          "event_type": "step_started",
          "actor": "client",
          "summary": "Calling Frankfurter Currency Converter for ConvertCurrency.",
          "data": {
            "step_id": "g3",
            "tool_id": "frankfurter-currency",
            "params": {
              "amount": 200.0,
              "from_currency": "USD",
              "to_currency": "PKR"
            },
            "input_bindings": {
              "amount": "$task.amount",
              "from_currency": "$task.from_currency",
              "to_currency": "$task.to_currency"
            }
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 23,
          "timestamp": "2026-10-24T13:45:55.924192Z",
          "event_type": "step_succeeded",
          "actor": "provider",
          "summary": "Frankfurter Currency Converter returned a schema-valid result.",
          "data": {
            "step_id": "g3",
            "tool_id": "frankfurter-currency",
            "status": "completed",
            "source": "fixture",
            "cached": false,
            "latency_ms": 2.96,
            "output": {
              "conversion": {
                "amount": 55700.0,
                "currency": "PKR",
                "rate": 278.5,
                "from": "USD",
                "to": "PKR",
                "date": "2026-10-24",
                "source": "offline fixture"
              }
            },
            "substituted_from": null
          }
        },
        {
          "task_id": "task_2a4ef4f5c5b9",
          "seq": 24,
          "timestamp": "2026-10-24T13:45:55.929335Z",
          "event_type": "task_completed",
          "actor": "client",
          "summary": "Task finished with status completed.",
          "data": {
            "status": "completed",
            "answer": "Weather for Lahore on 2026-10-25: high 37.9 C, low 28.3 C, 6% chance of precipitation. 200.00 USD is approximately 55,700.00 PKR at rate 278.5 (2026-10-24). A provider failed during execution, so the Client recovered the chain with a type-compatible substitute behind the circuit breaker.",
            "failures": [],
            "metrics": {
              "total_ms": 166.06,
              "retrieval_ms": 0.8220000001983863,
              "verification_ms": 16.58580000002985,
              "composition_ms": 0.17,
              "execution_ms": 98.88,
              "substitution_ms": 31.894499999907566,
              "tokens": 0
            },
            "mode": "offline"
          }
        }
      ],
      "warnings": [
        "Offline demo fixture; no live provider was contacted."
      ],
      "duration_ms": 169.17,
      "mode": "offline",
      "metrics": {
        "total_ms": 166.06,
        "retrieval_ms": 0.8220000001983863,
        "verification_ms": 16.58580000002985,
        "composition_ms": 0.17,
        "execution_ms": 98.88,
        "substitution_ms": 31.894499999907566,
        "tokens": 0
      },
      "error": null,
      "created_at": "2026-10-24T13:45:55.929335Z"
    },
    {
      "task_id": "task_c93bb2c064ed",
      "task": "How many students are enrolled in the BS Artificial Intelligence program?",
      "status": "completed",
      "answer": "The database returned students = 8. Executed SQL: SELECT COUNT(*) AS students FROM students WHERE program = ?",
      "subgoals": [
        {
          "id": "g1",
          "capability": "QueryStructuredData",
          "description": "Answer this question using the read-only university database: How many students are enrolled in the BS Artificial Intelligence program?",
          "intent": "database query",
          "slots": {
            "question": "How many students are enrolled in the BS Artificial Intelligence program?"
          },
          "depends_on": [],
          "branch": "database"
        }
      ],
      "candidate_lists": [
        {
          "message_id": "msg_a0c8f6a2d32a",
          "timestamp": "2026-10-24T13:45:55.960919Z",
          "sender": "client",
          "recipient": "interface",
          "correlation_id": "task_c93bb2c064ed",
          "kind": "CandidateList",
          "task_id": "task_c93bb2c064ed",
          "subgoal_id": "g1",
          "capability": "QueryStructuredData",
          "candidates": [
            {
              "tool": {
                "id": "university-sql",
                "name": "University Read-only SQL Provider",
                "provider_id": "university-db",
                "description": "Answer questions about students, programs, courses and enrolment using a local read-only university SQL database.",
                "capability": "QueryStructuredData",
                "inputs": [
                  {
                    "concept": "NaturalLanguageQuery",
                    "name": "question",
                    "unit": null,
                    "datatype": "string",
                    "required": true,
                    "description": "Question about the sample university database.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "TabularAnswer",
                    "name": "table",
                    "unit": null,
                    "datatype": "object",
                    "required": true,
                    "description": "Query result rows with the SQL that produced them.",
                    "fields": [
                      "columns",
                      "rows",
                      "sql",
                      "row_count"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Uses a read-only connection to the local sample database.",
                    "label": "Verified",
                    "evidence": "Enforced in the Provider with a query-only connection.",
                    "checked_at": null
                  },
                  {
                    "text": "Rejects writes and non-allow-listed tables.",
                    "label": "Verified",
                    "evidence": "SQL guard and allow-list checked before execution.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "database",
                  "sql",
                  "students",
                  "student",
                  "program",
                  "programs",
                  "enrolment",
                  "enrollment",
                  "gpa",
                  "courses",
                  "university",
                  "count",
                  "rows"
                ],
                "docs_url": "",
                "price": 0.0,
                "probe_eligible": true,
                "execution": "live",
                "tags": [
                  "database",
                  "local"
                ]
              },
              "relevance": 1.0,
              "trust": 0.5,
              "score": 0.5,
              "rank": 1,
              "reasons": [
                "lexical similarity 0.53",
                "capability QueryStructuredData matched",
                "typed inputs fit the sub-goal",
                "trust 0.50",
                "claim label Verified"
              ],
              "claim_label": "Verified",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            }
          ]
        }
      ],
      "plan": {
        "plan_id": "plan_7e657a60a0e5",
        "task_id": "task_c93bb2c064ed",
        "steps": [
          {
            "id": "g1",
            "subgoal_id": "g1",
            "tool_id": "university-sql",
            "tool_name": "University Read-only SQL Provider",
            "capability": "QueryStructuredData",
            "branch": "database",
            "input_bindings": {
              "question": "$task.question"
            },
            "params": {
              "question": "How many students are enrolled in the BS Artificial Intelligence program?"
            },
            "link_checks": [],
            "status": "completed",
            "output": {
              "table": {
                "columns": [
                  "students"
                ],
                "rows": [
                  {
                    "students": 8
                  }
                ],
                "sql": "SELECT COUNT(*) AS students FROM students WHERE program = ?",
                "row_count": 1
              }
            },
            "error": null,
            "latency_ms": 5.94,
            "cached": false,
            "source": "fixture",
            "substituted_from": null
          }
        ],
        "branches": {
          "database": [
            "g1"
          ]
        },
        "valid": true,
        "errors": [],
        "created_at": "2026-10-24T13:45:55.962332Z"
      },
      "trace": [
        {
          "task_id": "task_c93bb2c064ed",
          "seq": 1,
          "timestamp": "2026-10-24T13:45:55.931344Z",
          "event_type": "task_started",
          "actor": "client",
          "summary": "Task received by the Client agent.",
          "data": {
            "task": "How many students are enrolled in the BS Artificial Intelligence program?",
            "mode": "offline"
          }
        },
        {
          "task_id": "task_c93bb2c064ed",
          "seq": 2,
          "timestamp": "2026-10-24T13:45:55.945187Z",
          "event_type": "task_decomposed",
          "actor": "client",
          "summary": "Task decomposed into 1 sub-goal(s).",
          "data": {
            "subgoals": [
              {
                "id": "g1",
                "capability": "QueryStructuredData",
                "description": "Answer this question using the read-only university database: How many students are enrolled in the BS Artificial Intelligence program?",
                "intent": "database query",
                "slots": {
                  "question": "How many students are enrolled in the BS Artificial Intelligence program?"
                },
                "depends_on": [],
                "branch": "database"
              }
            ]
          }
        },
        {
          "task_id": "task_c93bb2c064ed",
          "seq": 3,
          "timestamp": "2026-10-24T13:45:55.945187Z",
          "event_type": "graphrag_shortlist",
          "actor": "client",
          "summary": "Retrieved 1 candidate(s) for QueryStructuredData; 1 survived the filter.",
          "data": {
            "subgoal_id": "g1",
            "query": "Answer this question using the read-only university database: How many students are enrolled in the BS Artificial Intelligence program? How many students are enrolled in the BS Artificial Intelligence program?",
            "retrieved": [
              {
                "tool_id": "university-sql",
                "relevance": 1.0,
                "reasons": [
                  "lexical similarity 0.53"
                ]
              }
            ],
            "filtered": []
          }
        },
        {
          "task_id": "task_c93bb2c064ed",
          "seq": 4,
          "timestamp": "2026-10-24T13:45:55.945187Z",
          "event_type": "claims_verified",
          "actor": "auditor",
          "summary": "Claim labels returned for the candidate list.",
          "data": {
            "subgoal_id": "g1",
            "overall": {
              "university-sql": "Verified"
            }
          }
        },
        {
          "task_id": "task_c93bb2c064ed",
          "seq": 5,
          "timestamp": "2026-10-24T13:45:55.962332Z",
          "event_type": "candidate_ranking",
          "actor": "client",
          "summary": "Ranked 1 candidate(s) for QueryStructuredData.",
          "data": {
            "subgoal_id": "g1",
            "ranked": [
              {
                "tool_id": "university-sql",
                "name": "University Read-only SQL Provider",
                "score": 0.5,
                "relevance": 1.0,
                "trust": 0.5,
                "claim_label": "Verified",
                "eligible": true,
                "breaker": "closed"
              }
            ]
          }
        },
        {
          "task_id": "task_c93bb2c064ed",
          "seq": 6,
          "timestamp": "2026-10-24T13:45:55.962332Z",
          "event_type": "planning_finished",
          "actor": "client",
          "summary": "Task decomposition and candidate matching finished.",
          "data": {
            "elapsed_ms": 20.95
          }
        },
        {
          "task_id": "task_c93bb2c064ed",
          "seq": 7,
          "timestamp": "2026-10-24T13:45:55.962332Z",
          "event_type": "chain_composed",
          "actor": "client",
          "summary": "A valid execution chain was composed.",
          "data": {
            "valid": true,
            "steps": [
              {
                "id": "g1",
                "subgoal_id": "g1",
                "tool_id": "university-sql",
                "tool_name": "University Read-only SQL Provider",
                "capability": "QueryStructuredData",
                "branch": "database",
                "input_bindings": {
                  "question": "$task.question"
                },
                "params": {},
                "link_checks": [],
                "status": "pending",
                "output": null,
                "error": null,
                "latency_ms": 0.0,
                "cached": false,
                "source": "",
                "substituted_from": null
              }
            ],
            "errors": []
          }
        },
        {
          "task_id": "task_c93bb2c064ed",
          "seq": 8,
          "timestamp": "2026-10-24T13:45:55.973605Z",
          "event_type": "step_started",
          "actor": "client",
          "summary": "Calling University Read-only SQL Provider for QueryStructuredData.",
          "data": {
            "step_id": "g1",
            "tool_id": "university-sql",
            "params": {
              "question": "How many students are enrolled in the BS Artificial Intelligence program?"
            },
            "input_bindings": {
              "question": "$task.question"
            }
          }
        },
        {
          "task_id": "task_c93bb2c064ed",
          "seq": 9,
          "timestamp": "2026-10-24T13:45:56.001037Z",
          "event_type": "step_succeeded",
          "actor": "provider",
          "summary": "University Read-only SQL Provider returned a schema-valid result.",
          "data": {
            "step_id": "g1",
            "tool_id": "university-sql",
            "status": "completed",
            "source": "fixture",
            "cached": false,
            "latency_ms": 5.94,
            "output": {
              "table": {
                "columns": [
                  "students"
                ],
                "rows": [
                  {
                    "students": 8
                  }
                ],
                "sql": "SELECT COUNT(*) AS students FROM students WHERE program = ?",
                "row_count": 1
              }
            },
            "substituted_from": null
          }
        },
        {
          "task_id": "task_c93bb2c064ed",
          "seq": 10,
          "timestamp": "2026-10-24T13:45:56.007064Z",
          "event_type": "task_completed",
          "actor": "client",
          "summary": "Task finished with status completed.",
          "data": {
            "status": "completed",
            "answer": "The database returned students = 8. Executed SQL: SELECT COUNT(*) AS students FROM students WHERE program = ?",
            "failures": [],
            "metrics": {
              "total_ms": 66.83,
              "retrieval_ms": 0.17450000018470746,
              "verification_ms": 6.035599999904662,
              "composition_ms": 0.07,
              "execution_ms": 33.95,
              "substitution_ms": 0.0,
              "tokens": 0
            },
            "mode": "offline"
          }
        }
      ],
      "warnings": [
        "Offline demo fixture; no live provider was contacted."
      ],
      "duration_ms": 69.99,
      "mode": "offline",
      "metrics": {
        "total_ms": 66.83,
        "retrieval_ms": 0.17450000018470746,
        "verification_ms": 6.035599999904662,
        "composition_ms": 0.07,
        "execution_ms": 33.95,
        "substitution_ms": 0.0,
        "tokens": 0
      },
      "error": null,
      "created_at": "2026-10-24T13:45:56.007064Z"
    },
    {
      "task_id": "task_c71492081236",
      "task": "Which public holidays does Pakistan have in 2026?",
      "status": "completed",
      "answer": "5 public holidays found. 2026-02-05 Kashmir Solidarity Day; 2026-03-23 Pakistan Day; 2026-05-01 Labour Day; 2026-08-14 Independence Day; 2026-12-25 Christmas Day.",
      "subgoals": [
        {
          "id": "g1",
          "capability": "GetPublicHolidays",
          "description": "Public holidays in Pakistan for the year 2026.",
          "intent": "public holidays",
          "slots": {
            "country_code": "PK",
            "year": 2026,
            "country": "Pakistan"
          },
          "depends_on": [],
          "branch": "holidays"
        }
      ],
      "candidate_lists": [
        {
          "message_id": "msg_b4bb0dd29597",
          "timestamp": "2026-10-24T13:45:56.030788Z",
          "sender": "client",
          "recipient": "interface",
          "correlation_id": "task_c71492081236",
          "kind": "CandidateList",
          "task_id": "task_c71492081236",
          "subgoal_id": "g1",
          "capability": "GetPublicHolidays",
          "candidates": [
            {
              "tool": {
                "id": "nager-holidays",
                "name": "Nager.Date Public Holidays",
                "provider_id": "nager-date",
                "description": "List public holidays for a country and year, including local names and dates.",
                "capability": "GetPublicHolidays",
                "inputs": [
                  {
                    "concept": "CountryCode",
                    "name": "country_code",
                    "unit": null,
                    "datatype": "string",
                    "required": true,
                    "description": "ISO 3166-1 alpha-2 country code.",
                    "fields": []
                  },
                  {
                    "concept": "Number",
                    "name": "year",
                    "unit": null,
                    "datatype": "integer",
                    "required": true,
                    "description": "Calendar year.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "Holiday",
                    "name": "holidays",
                    "unit": null,
                    "datatype": "array",
                    "required": true,
                    "description": "Public holidays for the requested country and year.",
                    "fields": [
                      "date",
                      "name",
                      "local_name",
                      "country_code"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Returns public holidays by country and year.",
                    "label": "Supported",
                    "evidence": "Nager.Date API documentation.",
                    "checked_at": null
                  },
                  {
                    "text": "No API key is required.",
                    "label": "Supported",
                    "evidence": "Nager.Date public endpoint.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "holiday",
                  "holidays",
                  "public holiday",
                  "national holiday",
                  "calendar",
                  "eid",
                  "christmas",
                  "pakistan",
                  "country"
                ],
                "docs_url": "https://date.nager.at/Api",
                "price": 0.0,
                "probe_eligible": true,
                "execution": "live",
                "tags": [
                  "api",
                  "calendar",
                  "backup-eligible"
                ]
              },
              "relevance": 1.0,
              "trust": 0.5,
              "score": 0.5,
              "rank": 1,
              "reasons": [
                "lexical similarity 0.45",
                "capability GetPublicHolidays matched",
                "typed inputs fit the sub-goal",
                "trust 0.50",
                "claim label Supported"
              ],
              "claim_label": "Supported",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            },
            {
              "tool": {
                "id": "nager-holidays-backup",
                "name": "Nager.Date Public Holidays (Backup Mirror)",
                "provider_id": "nager-date-backup",
                "description": "Standby backup mirror used to test circuit-breaker substitution. Mirrors Nager.Date Public Holidays. List public holidays for a country and year, including local names and dates.",
                "capability": "GetPublicHolidays",
                "inputs": [
                  {
                    "concept": "CountryCode",
                    "name": "country_code",
                    "unit": null,
                    "datatype": "string",
                    "required": true,
                    "description": "ISO 3166-1 alpha-2 country code.",
                    "fields": []
                  },
                  {
                    "concept": "Number",
                    "name": "year",
                    "unit": null,
                    "datatype": "integer",
                    "required": true,
                    "description": "Calendar year.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "Holiday",
                    "name": "holidays",
                    "unit": null,
                    "datatype": "array",
                    "required": true,
                    "description": "Public holidays for the requested country and year.",
                    "fields": [
                      "date",
                      "name",
                      "local_name",
                      "country_code"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Returns public holidays by country and year.",
                    "label": "Unsupported",
                    "evidence": "Backup mirror; not independently verified.",
                    "checked_at": null
                  },
                  {
                    "text": "No API key is required.",
                    "label": "Unsupported",
                    "evidence": "Backup mirror; not independently verified.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "holiday",
                  "holidays",
                  "public holiday",
                  "national holiday",
                  "calendar",
                  "eid",
                  "christmas",
                  "pakistan",
                  "country"
                ],
                "docs_url": "https://date.nager.at/Api",
                "price": 0.0,
                "probe_eligible": false,
                "execution": "mock",
                "tags": [
                  "api",
                  "calendar",
                  "backup-eligible",
                  "backup"
                ]
              },
              "relevance": 0.9385,
              "trust": 0.5,
              "score": 0.4693,
              "rank": 2,
              "reasons": [
                "lexical similarity 0.42",
                "capability GetPublicHolidays matched",
                "typed inputs fit the sub-goal",
                "trust 0.50",
                "claim label Unsupported"
              ],
              "claim_label": "Unsupported",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            }
          ]
        }
      ],
      "plan": {
        "plan_id": "plan_33d4414ef299",
        "task_id": "task_c71492081236",
        "steps": [
          {
            "id": "g1",
            "subgoal_id": "g1",
            "tool_id": "nager-holidays",
            "tool_name": "Nager.Date Public Holidays",
            "capability": "GetPublicHolidays",
            "branch": "holidays",
            "input_bindings": {
              "country_code": "$task.country_code",
              "year": "$task.year"
            },
            "params": {
              "country_code": "PK",
              "year": 2026
            },
            "link_checks": [],
            "status": "completed",
            "output": {
              "holidays": [
                {
                  "date": "2026-02-05",
                  "name": "Kashmir Solidarity Day",
                  "local_name": "یوم یکجہتی کشمیر",
                  "country_code": "PK"
                },
                {
                  "date": "2026-03-23",
                  "name": "Pakistan Day",
                  "local_name": "یوم پاکستان",
                  "country_code": "PK"
                },
                {
                  "date": "2026-05-01",
                  "name": "Labour Day",
                  "local_name": "یوم مزدور",
                  "country_code": "PK"
                },
                {
                  "date": "2026-08-14",
                  "name": "Independence Day",
                  "local_name": "یوم آزادی",
                  "country_code": "PK"
                },
                {
                  "date": "2026-12-25",
                  "name": "Christmas Day",
                  "local_name": "کرسمس",
                  "country_code": "PK"
                }
              ]
            },
            "error": null,
            "latency_ms": 2.78,
            "cached": false,
            "source": "fixture",
            "substituted_from": null
          }
        ],
        "branches": {
          "holidays": [
            "g1"
          ]
        },
        "valid": true,
        "errors": [],
        "created_at": "2026-10-24T13:45:56.040645Z"
      },
      "trace": [
        {
          "task_id": "task_c71492081236",
          "seq": 1,
          "timestamp": "2026-10-24T13:45:56.017388Z",
          "event_type": "task_started",
          "actor": "client",
          "summary": "Task received by the Client agent.",
          "data": {
            "task": "Which public holidays does Pakistan have in 2026?",
            "mode": "offline"
          }
        },
        {
          "task_id": "task_c71492081236",
          "seq": 2,
          "timestamp": "2026-10-24T13:45:56.023426Z",
          "event_type": "task_decomposed",
          "actor": "client",
          "summary": "Task decomposed into 1 sub-goal(s).",
          "data": {
            "subgoals": [
              {
                "id": "g1",
                "capability": "GetPublicHolidays",
                "description": "Public holidays in Pakistan for the year 2026.",
                "intent": "public holidays",
                "slots": {
                  "country_code": "PK",
                  "year": 2026,
                  "country": "Pakistan"
                },
                "depends_on": [],
                "branch": "holidays"
              }
            ]
          }
        },
        {
          "task_id": "task_c71492081236",
          "seq": 3,
          "timestamp": "2026-10-24T13:45:56.026951Z",
          "event_type": "graphrag_shortlist",
          "actor": "client",
          "summary": "Retrieved 2 candidate(s) for GetPublicHolidays; 2 survived the filter.",
          "data": {
            "subgoal_id": "g1",
            "query": "Public holidays in Pakistan for the year 2026. PK 2026 Pakistan",
            "retrieved": [
              {
                "tool_id": "nager-holidays",
                "relevance": 1.0,
                "reasons": [
                  "lexical similarity 0.45"
                ]
              },
              {
                "tool_id": "nager-holidays-backup",
                "relevance": 0.9385,
                "reasons": [
                  "lexical similarity 0.42"
                ]
              }
            ],
            "filtered": []
          }
        },
        {
          "task_id": "task_c71492081236",
          "seq": 4,
          "timestamp": "2026-10-24T13:45:56.030788Z",
          "event_type": "claims_verified",
          "actor": "auditor",
          "summary": "Claim labels returned for the candidate list.",
          "data": {
            "subgoal_id": "g1",
            "overall": {
              "nager-holidays": "Supported",
              "nager-holidays-backup": "Unsupported"
            }
          }
        },
        {
          "task_id": "task_c71492081236",
          "seq": 5,
          "timestamp": "2026-10-24T13:45:56.040645Z",
          "event_type": "candidate_ranking",
          "actor": "client",
          "summary": "Ranked 2 candidate(s) for GetPublicHolidays.",
          "data": {
            "subgoal_id": "g1",
            "ranked": [
              {
                "tool_id": "nager-holidays",
                "name": "Nager.Date Public Holidays",
                "score": 0.5,
                "relevance": 1.0,
                "trust": 0.5,
                "claim_label": "Supported",
                "eligible": true,
                "breaker": "closed"
              },
              {
                "tool_id": "nager-holidays-backup",
                "name": "Nager.Date Public Holidays (Backup Mirror)",
                "score": 0.4693,
                "relevance": 0.9385,
                "trust": 0.5,
                "claim_label": "Unsupported",
                "eligible": true,
                "breaker": "closed"
              }
            ]
          }
        },
        {
          "task_id": "task_c71492081236",
          "seq": 6,
          "timestamp": "2026-10-24T13:45:56.040645Z",
          "event_type": "planning_finished",
          "actor": "client",
          "summary": "Task decomposition and candidate matching finished.",
          "data": {
            "elapsed_ms": 22.03
          }
        },
        {
          "task_id": "task_c71492081236",
          "seq": 7,
          "timestamp": "2026-10-24T13:45:56.040645Z",
          "event_type": "chain_composed",
          "actor": "client",
          "summary": "A valid execution chain was composed.",
          "data": {
            "valid": true,
            "steps": [
              {
                "id": "g1",
                "subgoal_id": "g1",
                "tool_id": "nager-holidays",
                "tool_name": "Nager.Date Public Holidays",
                "capability": "GetPublicHolidays",
                "branch": "holidays",
                "input_bindings": {
                  "country_code": "$task.country_code",
                  "year": "$task.year"
                },
                "params": {},
                "link_checks": [],
                "status": "pending",
                "output": null,
                "error": null,
                "latency_ms": 0.0,
                "cached": false,
                "source": "",
                "substituted_from": null
              }
            ],
            "errors": []
          }
        },
        {
          "task_id": "task_c71492081236",
          "seq": 8,
          "timestamp": "2026-10-24T13:45:56.040645Z",
          "event_type": "step_started",
          "actor": "client",
          "summary": "Calling Nager.Date Public Holidays for GetPublicHolidays.",
          "data": {
            "step_id": "g1",
            "tool_id": "nager-holidays",
            "params": {
              "country_code": "PK",
              "year": 2026
            },
            "input_bindings": {
              "country_code": "$task.country_code",
              "year": "$task.year"
            }
          }
        },
        {
          "task_id": "task_c71492081236",
          "seq": 9,
          "timestamp": "2026-10-24T13:45:56.056431Z",
          "event_type": "step_succeeded",
          "actor": "provider",
          "summary": "Nager.Date Public Holidays returned a schema-valid result.",
          "data": {
            "step_id": "g1",
            "tool_id": "nager-holidays",
            "status": "completed",
            "source": "fixture",
            "cached": false,
            "latency_ms": 2.78,
            "output": {
              "holidays": [
                {
                  "date": "2026-02-05",
                  "name": "Kashmir Solidarity Day",
                  "local_name": "یوم یکجہتی کشمیر",
                  "country_code": "PK"
                },
                {
                  "date": "2026-03-23",
                  "name": "Pakistan Day",
                  "local_name": "یوم پاکستان",
                  "country_code": "PK"
                },
                {
                  "date": "2026-05-01",
                  "name": "Labour Day",
                  "local_name": "یوم مزدور",
                  "country_code": "PK"
                },
                {
                  "date": "2026-08-14",
                  "name": "Independence Day",
                  "local_name": "یوم آزادی",
                  "country_code": "PK"
                },
                {
                  "date": "2026-12-25",
                  "name": "Christmas Day",
                  "local_name": "کرسمس",
                  "country_code": "PK"
                }
              ]
            },
            "substituted_from": null
          }
        },
        {
          "task_id": "task_c71492081236",
          "seq": 10,
          "timestamp": "2026-10-24T13:45:56.073892Z",
          "event_type": "task_completed",
          "actor": "client",
          "summary": "Task finished with status completed.",
          "data": {
            "status": "completed",
            "answer": "5 public holidays found. 2026-02-05 Kashmir Solidarity Day; 2026-03-23 Pakistan Day; 2026-05-01 Labour Day; 2026-08-14 Independence Day; 2026-12-25 Christmas Day.",
            "failures": [],
            "metrics": {
              "total_ms": 57.55,
              "retrieval_ms": 0.3788000001350156,
              "verification_ms": 6.026100000099177,
              "composition_ms": 0.11,
              "execution_ms": 23.98,
              "substitution_ms": 0.0,
              "tokens": 0
            },
            "mode": "offline"
          }
        }
      ],
      "warnings": [
        "Offline demo fixture; no live provider was contacted."
      ],
      "duration_ms": 60.7,
      "mode": "offline",
      "metrics": {
        "total_ms": 57.55,
        "retrieval_ms": 0.3788000001350156,
        "verification_ms": 6.026100000099177,
        "composition_ms": 0.11,
        "execution_ms": 23.98,
        "substitution_ms": 0.0,
        "tokens": 0
      },
      "error": null,
      "created_at": "2026-10-24T13:45:56.073892Z"
    },
    {
      "task_id": "task_773d82f5f573",
      "task": "Find recent research papers on GraphRAG.",
      "status": "completed",
      "answer": "Top research results: Retrieval and verification patterns for GraphRAG (https://arxiv.org/search/?query=GraphRAG&searchtype=all); Knowledge-graph grounding for tool-using agents: GraphRAG (https://arxiv.org/search/?query=GraphRAG&searchtype=all).",
      "subgoals": [
        {
          "id": "g1",
          "capability": "SearchResearchPapers",
          "description": "Recent research papers about GraphRAG.",
          "intent": "research search",
          "slots": {
            "query": "GraphRAG"
          },
          "depends_on": [],
          "branch": "research"
        }
      ],
      "candidate_lists": [
        {
          "message_id": "msg_8994db050a6d",
          "timestamp": "2026-10-24T13:45:56.102543Z",
          "sender": "client",
          "recipient": "interface",
          "correlation_id": "task_773d82f5f573",
          "kind": "CandidateList",
          "task_id": "task_773d82f5f573",
          "subgoal_id": "g1",
          "capability": "SearchResearchPapers",
          "candidates": [
            {
              "tool": {
                "id": "arxiv-search",
                "name": "arXiv Research Search",
                "provider_id": "arxiv",
                "description": "Search recent research papers on arXiv by topic and return titles, summaries, authors and links.",
                "capability": "SearchResearchPapers",
                "inputs": [
                  {
                    "concept": "ResearchTopic",
                    "name": "query",
                    "unit": null,
                    "datatype": "string",
                    "required": true,
                    "description": "Research topic or keywords.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "ResearchPaper",
                    "name": "papers",
                    "unit": null,
                    "datatype": "array",
                    "required": true,
                    "description": "Ranked paper records.",
                    "fields": [
                      "title",
                      "summary",
                      "url",
                      "published",
                      "authors"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Searches arXiv metadata without an API key.",
                    "label": "Supported",
                    "evidence": "arXiv API documentation.",
                    "checked_at": null
                  },
                  {
                    "text": "Returns titles, summaries and links.",
                    "label": "Supported",
                    "evidence": "arXiv Atom feed schema.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "research",
                  "paper",
                  "papers",
                  "arxiv",
                  "study",
                  "literature",
                  "graphrag",
                  "ontology",
                  "llm",
                  "publication",
                  "science"
                ],
                "docs_url": "https://info.arxiv.org/help/api/index.html",
                "price": 0.0,
                "probe_eligible": true,
                "execution": "live",
                "tags": [
                  "api",
                  "research",
                  "backup-eligible"
                ]
              },
              "relevance": 1.0,
              "trust": 0.5,
              "score": 0.5,
              "rank": 1,
              "reasons": [
                "lexical similarity 0.44",
                "capability SearchResearchPapers matched",
                "typed inputs fit the sub-goal",
                "trust 0.50",
                "claim label Supported"
              ],
              "claim_label": "Supported",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            },
            {
              "tool": {
                "id": "arxiv-search-backup",
                "name": "arXiv Research Search (Backup Mirror)",
                "provider_id": "arxiv-backup",
                "description": "Standby backup mirror used to test circuit-breaker substitution. Mirrors arXiv Research Search. Search recent research papers on arXiv by topic and return titles, summaries, authors and links.",
                "capability": "SearchResearchPapers",
                "inputs": [
                  {
                    "concept": "ResearchTopic",
                    "name": "query",
                    "unit": null,
                    "datatype": "string",
                    "required": true,
                    "description": "Research topic or keywords.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "ResearchPaper",
                    "name": "papers",
                    "unit": null,
                    "datatype": "array",
                    "required": true,
                    "description": "Ranked paper records.",
                    "fields": [
                      "title",
                      "summary",
                      "url",
                      "published",
                      "authors"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Searches arXiv metadata without an API key.",
                    "label": "Unsupported",
                    "evidence": "Backup mirror; not independently verified.",
                    "checked_at": null
                  },
                  {
                    "text": "Returns titles, summaries and links.",
                    "label": "Unsupported",
                    "evidence": "Backup mirror; not independently verified.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "research",
                  "paper",
                  "papers",
                  "arxiv",
                  "study",
                  "literature",
                  "graphrag",
                  "ontology",
                  "llm",
                  "publication",
                  "science"
                ],
                "docs_url": "https://info.arxiv.org/help/api/index.html",
                "price": 0.0,
                "probe_eligible": false,
                "execution": "mock",
                "tags": [
                  "api",
                  "research",
                  "backup-eligible",
                  "backup"
                ]
              },
              "relevance": 0.9287,
              "trust": 0.5,
              "score": 0.4643,
              "rank": 2,
              "reasons": [
                "lexical similarity 0.41",
                "capability SearchResearchPapers matched",
                "typed inputs fit the sub-goal",
                "trust 0.50",
                "claim label Unsupported"
              ],
              "claim_label": "Unsupported",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            }
          ]
        }
      ],
      "plan": {
        "plan_id": "plan_bfb7f716cd7f",
        "task_id": "task_773d82f5f573",
        "steps": [
          {
            "id": "g1",
            "subgoal_id": "g1",
            "tool_id": "arxiv-search",
            "tool_name": "arXiv Research Search",
            "capability": "SearchResearchPapers",
            "branch": "research",
            "input_bindings": {
              "query": "$task.query"
            },
            "params": {
              "query": "GraphRAG"
            },
            "link_checks": [],
            "status": "completed",
            "output": {
              "papers": [
                {
                  "title": "Retrieval and verification patterns for GraphRAG",
                  "summary": "Offline demonstration record. A live arXiv search returns the actual papers for the topic 'GraphRAG'.",
                  "url": "https://arxiv.org/search/?query=GraphRAG&searchtype=all",
                  "published": "2026-01-01T00:00:00Z",
                  "authors": [
                    "Offline fixture"
                  ]
                },
                {
                  "title": "Knowledge-graph grounding for tool-using agents: GraphRAG",
                  "summary": "Offline demonstration record used when the arXiv API is unreachable. It is clearly marked as a fixture and is not a real publication.",
                  "url": "https://arxiv.org/search/?query=GraphRAG&searchtype=all",
                  "published": "2026-01-01T00:00:00Z",
                  "authors": [
                    "Offline fixture"
                  ]
                }
              ]
            },
            "error": null,
            "latency_ms": 3.1,
            "cached": false,
            "source": "fixture",
            "substituted_from": null
          }
        ],
        "branches": {
          "research": [
            "g1"
          ]
        },
        "valid": true,
        "errors": [],
        "created_at": "2026-10-24T13:45:56.104294Z"
      },
      "trace": [
        {
          "task_id": "task_773d82f5f573",
          "seq": 1,
          "timestamp": "2026-10-24T13:45:56.073892Z",
          "event_type": "task_started",
          "actor": "client",
          "summary": "Task received by the Client agent.",
          "data": {
            "task": "Find recent research papers on GraphRAG.",
            "mode": "offline"
          }
        },
        {
          "task_id": "task_773d82f5f573",
          "seq": 2,
          "timestamp": "2026-10-24T13:45:56.090486Z",
          "event_type": "task_decomposed",
          "actor": "client",
          "summary": "Task decomposed into 1 sub-goal(s).",
          "data": {
            "subgoals": [
              {
                "id": "g1",
                "capability": "SearchResearchPapers",
                "description": "Recent research papers about GraphRAG.",
                "intent": "research search",
                "slots": {
                  "query": "GraphRAG"
                },
                "depends_on": [],
                "branch": "research"
              }
            ]
          }
        },
        {
          "task_id": "task_773d82f5f573",
          "seq": 3,
          "timestamp": "2026-10-24T13:45:56.092497Z",
          "event_type": "graphrag_shortlist",
          "actor": "client",
          "summary": "Retrieved 2 candidate(s) for SearchResearchPapers; 2 survived the filter.",
          "data": {
            "subgoal_id": "g1",
            "query": "Recent research papers about GraphRAG. GraphRAG",
            "retrieved": [
              {
                "tool_id": "arxiv-search",
                "relevance": 1.0,
                "reasons": [
                  "lexical similarity 0.44"
                ]
              },
              {
                "tool_id": "arxiv-search-backup",
                "relevance": 0.9287,
                "reasons": [
                  "lexical similarity 0.41"
                ]
              }
            ],
            "filtered": []
          }
        },
        {
          "task_id": "task_773d82f5f573",
          "seq": 4,
          "timestamp": "2026-10-24T13:45:56.100533Z",
          "event_type": "claims_verified",
          "actor": "auditor",
          "summary": "Claim labels returned for the candidate list.",
          "data": {
            "subgoal_id": "g1",
            "overall": {
              "arxiv-search": "Supported",
              "arxiv-search-backup": "Unsupported"
            }
          }
        },
        {
          "task_id": "task_773d82f5f573",
          "seq": 5,
          "timestamp": "2026-10-24T13:45:56.104294Z",
          "event_type": "candidate_ranking",
          "actor": "client",
          "summary": "Ranked 2 candidate(s) for SearchResearchPapers.",
          "data": {
            "subgoal_id": "g1",
            "ranked": [
              {
                "tool_id": "arxiv-search",
                "name": "arXiv Research Search",
                "score": 0.5,
                "relevance": 1.0,
                "trust": 0.5,
                "claim_label": "Supported",
                "eligible": true,
                "breaker": "closed"
              },
              {
                "tool_id": "arxiv-search-backup",
                "name": "arXiv Research Search (Backup Mirror)",
                "score": 0.4643,
                "relevance": 0.9287,
                "trust": 0.5,
                "claim_label": "Unsupported",
                "eligible": true,
                "breaker": "closed"
              }
            ]
          }
        },
        {
          "task_id": "task_773d82f5f573",
          "seq": 6,
          "timestamp": "2026-10-24T13:45:56.104294Z",
          "event_type": "planning_finished",
          "actor": "client",
          "summary": "Task decomposition and candidate matching finished.",
          "data": {
            "elapsed_ms": 19.13
          }
        },
        {
          "task_id": "task_773d82f5f573",
          "seq": 7,
          "timestamp": "2026-10-24T13:45:56.104294Z",
          "event_type": "chain_composed",
          "actor": "client",
          "summary": "A valid execution chain was composed.",
          "data": {
            "valid": true,
            "steps": [
              {
                "id": "g1",
                "subgoal_id": "g1",
                "tool_id": "arxiv-search",
                "tool_name": "arXiv Research Search",
                "capability": "SearchResearchPapers",
                "branch": "research",
                "input_bindings": {
                  "query": "$task.query"
                },
                "params": {},
                "link_checks": [],
                "status": "pending",
                "output": null,
                "error": null,
                "latency_ms": 0.0,
                "cached": false,
                "source": "",
                "substituted_from": null
              }
            ],
            "errors": []
          }
        },
        {
          "task_id": "task_773d82f5f573",
          "seq": 8,
          "timestamp": "2026-10-24T13:45:56.104294Z",
          "event_type": "step_started",
          "actor": "client",
          "summary": "Calling arXiv Research Search for SearchResearchPapers.",
          "data": {
            "step_id": "g1",
            "tool_id": "arxiv-search",
            "params": {
              "query": "GraphRAG"
            },
            "input_bindings": {
              "query": "$task.query"
            }
          }
        },
        {
          "task_id": "task_773d82f5f573",
          "seq": 9,
          "timestamp": "2026-10-24T13:45:56.136219Z",
          "event_type": "step_succeeded",
          "actor": "provider",
          "summary": "arXiv Research Search returned a schema-valid result.",
          "data": {
            "step_id": "g1",
            "tool_id": "arxiv-search",
            "status": "completed",
            "source": "fixture",
            "cached": false,
            "latency_ms": 3.1,
            "output": {
              "papers": [
                {
                  "title": "Retrieval and verification patterns for GraphRAG",
                  "summary": "Offline demonstration record. A live arXiv search returns the actual papers for the topic 'GraphRAG'.",
                  "url": "https://arxiv.org/search/?query=GraphRAG&searchtype=all",
                  "published": "2026-01-01T00:00:00Z",
                  "authors": [
                    "Offline fixture"
                  ]
                },
                {
                  "title": "Knowledge-graph grounding for tool-using agents: GraphRAG",
                  "summary": "Offline demonstration record used when the arXiv API is unreachable. It is clearly marked as a fixture and is not a real publication.",
                  "url": "https://arxiv.org/search/?query=GraphRAG&searchtype=all",
                  "published": "2026-01-01T00:00:00Z",
                  "authors": [
                    "Offline fixture"
                  ]
                }
              ]
            },
            "substituted_from": null
          }
        },
        {
          "task_id": "task_773d82f5f573",
          "seq": 10,
          "timestamp": "2026-10-24T13:45:56.136219Z",
          "event_type": "task_completed",
          "actor": "client",
          "summary": "Task finished with status completed.",
          "data": {
            "status": "completed",
            "answer": "Top research results: Retrieval and verification patterns for GraphRAG (https://arxiv.org/search/?query=GraphRAG&searchtype=all); Knowledge-graph grounding for tool-using agents: GraphRAG (https://arxiv.org/search/?query=GraphRAG&searchtype=all).",
            "failures": [],
            "metrics": {
              "total_ms": 60.83,
              "retrieval_ms": 0.13080000007903436,
              "verification_ms": 4.8606000000290805,
              "composition_ms": 0.11,
              "execution_ms": 29.88,
              "substitution_ms": 0.0,
              "tokens": 0
            },
            "mode": "offline"
          }
        }
      ],
      "warnings": [
        "Offline demo fixture; no live provider was contacted."
      ],
      "duration_ms": 63.98,
      "mode": "offline",
      "metrics": {
        "total_ms": 60.83,
        "retrieval_ms": 0.13080000007903436,
        "verification_ms": 4.8606000000290805,
        "composition_ms": 0.11,
        "execution_ms": 29.88,
        "substitution_ms": 0.0,
        "tokens": 0
      },
      "error": null,
      "created_at": "2026-10-24T13:45:56.136219Z"
    },
    {
      "task_id": "task_76de6fed3338",
      "task": "According to the uploaded document, what is the main goal of the project?",
      "status": "completed",
      "answer": "The main goal is to prove type-safe composition and self-healing. (Source: project-brief.txt.)",
      "subgoals": [
        {
          "id": "g1",
          "capability": "AnswerFromDocument",
          "description": "Answer this question from the uploaded document: According to the uploaded document, what is the main goal of the project?",
          "intent": "document question answering",
          "slots": {
            "question": "According to the uploaded document, what is the main goal of the project?"
          },
          "depends_on": [],
          "branch": "document"
        }
      ],
      "candidate_lists": [
        {
          "message_id": "msg_d2bedfce7f88",
          "timestamp": "2026-10-24T13:47:53.555678Z",
          "sender": "client",
          "recipient": "interface",
          "correlation_id": "task_76de6fed3338",
          "kind": "CandidateList",
          "task_id": "task_76de6fed3338",
          "subgoal_id": "g1",
          "capability": "AnswerFromDocument",
          "candidates": [
            {
              "tool": {
                "id": "document-qa",
                "name": "Uploaded Document Question Answering",
                "provider_id": "document-service",
                "description": "Answer questions over a document uploaded by the developer, returning extractive citations from the document.",
                "capability": "AnswerFromDocument",
                "inputs": [
                  {
                    "concept": "DocumentQuestion",
                    "name": "question",
                    "unit": null,
                    "datatype": "string",
                    "required": true,
                    "description": "Question about the document.",
                    "fields": []
                  },
                  {
                    "concept": "DocumentReference",
                    "name": "document_id",
                    "unit": null,
                    "datatype": "string",
                    "required": false,
                    "description": "Uploaded document identifier; the most recent document is used by default.",
                    "fields": []
                  }
                ],
                "outputs": [
                  {
                    "concept": "AnswerFromDocument",
                    "name": "answer",
                    "unit": null,
                    "datatype": "object",
                    "required": true,
                    "description": "Answer grounded in quoted document passages.",
                    "fields": [
                      "answer",
                      "citations",
                      "document_id"
                    ]
                  }
                ],
                "claims": [
                  {
                    "text": "Answers from the uploaded document with citations.",
                    "label": "Supported",
                    "evidence": "Local extractive QA implementation; every answer includes a passage.",
                    "checked_at": null
                  },
                  {
                    "text": "Does not send document text to a paid service.",
                    "label": "Supported",
                    "evidence": "Local parsing and retrieval; the optional LLM is disabled by default.",
                    "checked_at": null
                  }
                ],
                "keywords": [
                  "document",
                  "file",
                  "uploaded",
                  "upload",
                  "pdf",
                  "docx",
                  "text",
                  "according",
                  "document says",
                  "paper",
                  "report",
                  "notes"
                ],
                "docs_url": "",
                "price": 0.0,
                "probe_eligible": false,
                "execution": "live",
                "tags": [
                  "document",
                  "local"
                ]
              },
              "relevance": 1.0,
              "trust": 0.5,
              "score": 0.5,
              "rank": 1,
              "reasons": [
                "lexical similarity 0.46",
                "capability AnswerFromDocument matched",
                "typed inputs fit the sub-goal",
                "trust 0.50",
                "claim label Supported"
              ],
              "claim_label": "Supported",
              "breaker_state": "closed",
              "demoted": false,
              "eligible": true
            }
          ]
        }
      ],
      "plan": {
        "plan_id": "plan_69b1381ebe32",
        "task_id": "task_76de6fed3338",
        "steps": [
          {
            "id": "g1",
            "subgoal_id": "g1",
            "tool_id": "document-qa",
            "tool_name": "Uploaded Document Question Answering",
            "capability": "AnswerFromDocument",
            "branch": "document",
            "input_bindings": {
              "question": "$task.question"
            },
            "params": {
              "question": "According to the uploaded document, what is the main goal of the project?"
            },
            "link_checks": [],
            "status": "completed",
            "output": {
              "answer": {
                "answer": "The main goal is to prove type-safe composition and self-healing.",
                "citations": [
                  {
                    "document_id": "doc_d4b193fd257a",
                    "name": "project-brief.txt",
                    "quote": "Project Atlas is a verified tool orchestration demo. The main goal is to prove type-safe composition and self-healing.",
                    "score": 0.3273
                  }
                ],
                "document_id": "doc_d4b193fd257a"
              }
            },
            "error": null,
            "latency_ms": 3.01,
            "cached": false,
            "source": "fixture",
            "substituted_from": null
          }
        ],
        "branches": {
          "document": [
            "g1"
          ]
        },
        "valid": true,
        "errors": [],
        "created_at": "2026-10-24T13:47:53.568810Z"
      },
      "trace": [
        {
          "task_id": "task_76de6fed3338",
          "seq": 1,
          "timestamp": "2026-10-24T13:47:53.540640Z",
          "event_type": "task_started",
          "actor": "client",
          "summary": "Task received by the Client agent.",
          "data": {
            "task": "According to the uploaded document, what is the main goal of the project?",
            "mode": "offline"
          }
        },
        {
          "task_id": "task_76de6fed3338",
          "seq": 2,
          "timestamp": "2026-10-24T13:47:53.552882Z",
          "event_type": "task_decomposed",
          "actor": "client",
          "summary": "Task decomposed into 1 sub-goal(s).",
          "data": {
            "subgoals": [
              {
                "id": "g1",
                "capability": "AnswerFromDocument",
                "description": "Answer this question from the uploaded document: According to the uploaded document, what is the main goal of the project?",
                "intent": "document question answering",
                "slots": {
                  "question": "According to the uploaded document, what is the main goal of the project?"
                },
                "depends_on": [],
                "branch": "document"
              }
            ]
          }
        },
        {
          "task_id": "task_76de6fed3338",
          "seq": 3,
          "timestamp": "2026-10-24T13:47:53.555678Z",
          "event_type": "graphrag_shortlist",
          "actor": "client",
          "summary": "Retrieved 1 candidate(s) for AnswerFromDocument; 1 survived the filter.",
          "data": {
            "subgoal_id": "g1",
            "query": "Answer this question from the uploaded document: According to the uploaded document, what is the main goal of the project? According to the uploaded document, what is the main goal of the project?",
            "retrieved": [
              {
                "tool_id": "document-qa",
                "relevance": 1.0,
                "reasons": [
                  "lexical similarity 0.46"
                ]
              }
            ],
            "filtered": []
          }
        },
        {
          "task_id": "task_76de6fed3338",
          "seq": 4,
          "timestamp": "2026-10-24T13:47:53.555678Z",
          "event_type": "claims_verified",
          "actor": "auditor",
          "summary": "Claim labels returned for the candidate list.",
          "data": {
            "subgoal_id": "g1",
            "overall": {
              "document-qa": "Supported"
            }
          }
        },
        {
          "task_id": "task_76de6fed3338",
          "seq": 5,
          "timestamp": "2026-10-24T13:47:53.568810Z",
          "event_type": "candidate_ranking",
          "actor": "client",
          "summary": "Ranked 1 candidate(s) for AnswerFromDocument.",
          "data": {
            "subgoal_id": "g1",
            "ranked": [
              {
                "tool_id": "document-qa",
                "name": "Uploaded Document Question Answering",
                "score": 0.5,
                "relevance": 1.0,
                "trust": 0.5,
                "claim_label": "Supported",
                "eligible": true,
                "breaker": "closed"
              }
            ]
          }
        },
        {
          "task_id": "task_76de6fed3338",
          "seq": 6,
          "timestamp": "2026-10-24T13:47:53.568810Z",
          "event_type": "planning_finished",
          "actor": "client",
          "summary": "Task decomposition and candidate matching finished.",
          "data": {
            "elapsed_ms": 22.14
          }
        },
        {
          "task_id": "task_76de6fed3338",
          "seq": 7,
          "timestamp": "2026-10-24T13:47:53.568810Z",
          "event_type": "chain_composed",
          "actor": "client",
          "summary": "A valid execution chain was composed.",
          "data": {
            "valid": true,
            "steps": [
              {
                "id": "g1",
                "subgoal_id": "g1",
                "tool_id": "document-qa",
                "tool_name": "Uploaded Document Question Answering",
                "capability": "AnswerFromDocument",
                "branch": "document",
                "input_bindings": {
                  "question": "$task.question"
                },
                "params": {},
                "link_checks": [],
                "status": "pending",
                "output": null,
                "error": null,
                "latency_ms": 0.0,
                "cached": false,
                "source": "",
                "substituted_from": null
              }
            ],
            "errors": []
          }
        },
        {
          "task_id": "task_76de6fed3338",
          "seq": 8,
          "timestamp": "2026-10-24T13:47:53.568810Z",
          "event_type": "step_started",
          "actor": "client",
          "summary": "Calling Uploaded Document Question Answering for AnswerFromDocument.",
          "data": {
            "step_id": "g1",
            "tool_id": "document-qa",
            "params": {
              "question": "According to the uploaded document, what is the main goal of the project?"
            },
            "input_bindings": {
              "question": "$task.question"
            }
          }
        },
        {
          "task_id": "task_76de6fed3338",
          "seq": 9,
          "timestamp": "2026-10-24T13:47:53.600470Z",
          "event_type": "step_succeeded",
          "actor": "provider",
          "summary": "Uploaded Document Question Answering returned a schema-valid result.",
          "data": {
            "step_id": "g1",
            "tool_id": "document-qa",
            "status": "completed",
            "source": "fixture",
            "cached": false,
            "latency_ms": 3.01,
            "output": {
              "answer": {
                "answer": "The main goal is to prove type-safe composition and self-healing.",
                "citations": [
                  {
                    "document_id": "doc_d4b193fd257a",
                    "name": "project-brief.txt",
                    "quote": "Project Atlas is a verified tool orchestration demo. The main goal is to prove type-safe composition and self-healing.",
                    "score": 0.3273
                  }
                ],
                "document_id": "doc_d4b193fd257a"
              }
            },
            "substituted_from": null
          }
        },
        {
          "task_id": "task_76de6fed3338",
          "seq": 10,
          "timestamp": "2026-10-24T13:47:53.600470Z",
          "event_type": "task_completed",
          "actor": "client",
          "summary": "Task finished with status completed.",
          "data": {
            "status": "completed",
            "answer": "The main goal is to prove type-safe composition and self-healing. (Source: project-brief.txt.)",
            "failures": [],
            "metrics": {
              "total_ms": 64.15,
              "retrieval_ms": 0.15159999998104468,
              "verification_ms": 5.993699999862656,
              "composition_ms": 0.15,
              "execution_ms": 29.84,
              "substitution_ms": 0.0,
              "tokens": 0
            },
            "mode": "offline"
          }
        }
      ],
      "warnings": [
        "Offline demo fixture; no live provider was contacted."
      ],
      "duration_ms": 67.63,
      "mode": "offline",
      "metrics": {
        "total_ms": 64.15,
        "retrieval_ms": 0.15159999998104468,
        "verification_ms": 5.993699999862656,
        "composition_ms": 0.15,
        "execution_ms": 29.84,
        "substitution_ms": 0.0,
        "tokens": 0
      },
      "error": null,
      "created_at": "2026-10-24T13:47:53.600470Z"
    }
  ],
  "documents": {
    "documents": [
      {
        "document_id": "doc_8bcaf2bd9dc4",
        "name": "project-brief.txt",
        "size_bytes": 118,
        "text_chars": 118,
        "created_at": "2026-10-24T13:45:56.169107+00:00"
      },
      {
        "document_id": "doc_a9751d1f633c",
        "name": "agent_bazaar_project_brief.txt",
        "size_bytes": 834,
        "text_chars": 834,
        "created_at": "2026-10-24T13:45:55.534792+00:00"
      }
    ]
  },
  "upload": {
    "document": {
      "document_id": "doc_8bcaf2bd9dc4",
      "name": "project-brief.txt",
      "size_bytes": 118,
      "text_chars": 118,
      "created_at": "2026-10-24T13:45:56.169107Z"
    },
    "documents": [
      {
        "document_id": "doc_8bcaf2bd9dc4",
        "name": "project-brief.txt",
        "size_bytes": 118,
        "text_chars": 118,
        "created_at": "2026-10-24T13:45:56.169107+00:00"
      },
      {
        "document_id": "doc_a9751d1f633c",
        "name": "agent_bazaar_project_brief.txt",
        "size_bytes": 834,
        "text_chars": 834,
        "created_at": "2026-10-24T13:45:55.534792+00:00"
      }
    ]
  },
  "correction": {
    "correction_id": "corr_a574916a09",
    "accepted": true,
    "staged": true,
    "violations": [],
    "message": "Correction passed ontology checks and is staged for the Mapper."
  },
  "listing": {
    "message_id": "msg_6b7cb036df22",
    "timestamp": "2026-10-24T13:47:39.163479Z",
    "sender": "mapper",
    "recipient": "client",
    "correlation_id": "req_a2b7a35d1df7",
    "kind": "MapResult",
    "tool_id": "listing_36cafdc019",
    "inputs": [
      {
        "concept": "DocumentQuestion",
        "name": "question",
        "unit": null,
        "datatype": "string",
        "required": true,
        "description": "",
        "fields": []
      },
      {
        "concept": "DocumentReference",
        "name": "document",
        "unit": null,
        "datatype": "string",
        "required": true,
        "description": "",
        "fields": []
      }
    ],
    "outputs": [
      {
        "concept": "AnswerFromDocument",
        "name": "answer",
        "unit": null,
        "datatype": "string",
        "required": true,
        "description": "",
        "fields": []
      }
    ],
    "violations": [],
    "accepted": true,
    "staged": true
  }
};
