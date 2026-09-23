# hungry-trails-data

Data files for the Hungry Trails Android app, published so the app can
download them as static files instead of asking shared public servers.

## summits.tsv.gz

Every named summit on Earth (`natural=peak` and `natural=volcano` nodes with a
`name`) from OpenStreetMap, one per line, tab-separated, gzipped:

    id  lat  lon  name  ele  prominence  name:en  int_name  alt_name

Empty columns are empty strings. Built with `world-summits.py` from the public
Overpass API, box by box. Published as a release asset; the app fetches
`releases/latest/download/summits.tsv.gz`.

## Licence

The data is © OpenStreetMap contributors and is made available under the
[Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
It is a derivative database of OpenStreetMap: you may use, share and adapt it,
provided you credit "© OpenStreetMap contributors" and keep any adapted
database under the ODbL. See https://www.openstreetmap.org/copyright.

`world-summits.py` is MIT-licensed.
