import GeoJSON from './node_modules/ol/format/GeoJSON';
import Map from './node_modules/ol/Map';
import VectorLayer from './node_modules/ol/layer/Vector';
import VectorSource from './node_modules/ol/source/Vector';
import View from './node_modules/ol/View';
import {Fill, Stroke, Style} from './node_modules/ol/style';

const style = new Style({
  fill: new Fill({
    color: '#eeeeee',
  }),
});

const vectorLayer = new VectorLayer({
  background: '#1a2b39',
  source: new VectorSource({
    url: 'https://openlayers.org/data/vector/ecoregions.json',
    format: new GeoJSON(),
  }),
  style: function (feature) {
    const color = feature.get('COLOR_NNH') || '#eeeeee';
    style.getFill().setColor(color);
    return style;
  },
});

var map = new ol.Map({
    target: 'map',
    layers: [
        vectorLayer,
      new ol.layer.Tile({
        source: new ol.source.OSM()
      })
    ],
    view: new ol.View({
      center: ol.proj.fromLonLat([20.03728668367604, 50.07333660761058]),
      zoom: 16,
      minZoom: 15,
      maxZoom: 18,
      nearest: true
    })
  });

const highlightStyle = new Style({
  stroke: new Stroke({
    color: 'rgba(255, 255, 255, 0.7)',
    width: 2,
  }),
});

const featureOverlay = new VectorLayer({
  source: new VectorSource(),
  map: map,
  style: highlightStyle,
});

let highlight;
const displayFeatureInfo = function (pixel) {
  vectorLayer.getFeatures(pixel).then(function (features) {
    const feature = features.length ? features[0] : undefined;
    const info = document.getElementById('info');
    if (features.length) {
      info.innerHTML = feature.get('ECO_NAME') + ': ' + feature.get('NNH_NAME');
    } else {
      info.innerHTML = '&nbsp;';
    }

    if (feature !== highlight) {
      if (highlight) {
        featureOverlay.getSource().removeFeature(highlight);
      }
      if (feature) {
        featureOverlay.getSource().addFeature(feature);
      }
      highlight = feature;
    }
  });
};

map.on('pointermove', function (evt) {
  if (evt.dragging) {
    return;
  }
  const pixel = map.getEventPixel(evt.originalEvent);
  displayFeatureInfo(pixel);
});

map.on('click', function (evt) {
  displayFeatureInfo(evt.pixel);
});
