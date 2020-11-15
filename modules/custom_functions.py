# -*- coding: utf-8 -*-
"""Funciones custom para tratar toda la interaccion web-chromecast
"""
import time
import datetime
import logging
import zeroconf
from geventwebsocket import WebSocketError
#import requests
#from gevent.pywsgi import WSGIServer
#from geventwebsocket import WebSocketHandler, WebSocketError
#import websockets
import pychromecast


IPS = []
UUIDS = []
CHROMECASTS = {}
ESTADOS = {}

def get_status():
    """Devuelve el estado actual de los chromecasts

    Returns:
        dict: diccionario de diccionarios con los estados
    """
    return ESTADOS

def init():
    """Devuelve el listado de nombres de chromecasts

    Returns:
        list listado de nombres de chromecasts
    """
    lista = []
    for cast in CHROMECASTS.values():
        lista.append(cast.device.friendly_name)
    lista.sort()
    return lista

def update_status(listener, status):
    """Actualiza el diccionario de estados

    Args:
        listener (Listener): objeto listener que detecta llama a esta funcion
        status (Response): respuesta del chromecast con el cambio de estado
    """
    cast = str(listener.cast.device.friendly_name)
    listener_aux = listener.__class__.__name__

    # si no existe la clave la creo como un diccionario vacio
    ESTADOS[cast] = ESTADOS.get(cast, {})
    ESTADOS[cast]['uuid'] = str(listener.cast.device.uuid)
    ESTADOS[cast]['cast'] = cast

    lookup_atributos = {
        'volume_level': '{:.2f}'.format(status.volume_level),
        'title': status.title,
        'subtitle': status.media_metadata.get('subtitle', None),
        'series_title': status.series_title,
        'season': status.season,
        'episode': status.episode,
        'artist': status.artist,
        'album_name': status.album_name,
        'track': status.track,
        'images': status.images[0].get('url', None),
        'player_state': status.player_state,
        'volume_muted': status.volume_muted,
        'status_text': status.status_text,
        'icon_url': status.icon_url
    }

    lookup_claves = {
        'volume_level': 'volumen',
        'title': 'titulo',
        'subtitle': 'subtitulo',
        'series_title': 'serie',
        'season': 'temporada',
        'episode': 'episodio',
        'artist': 'artista',
        'album_name': 'album',
        'track': 'pista',
        'images': 'imagen',
        'player_state': 'estado',
        'volume_muted': 'mute',
        'status_text': 'texto',
        'icon_url': 'icono'
    }

    lookup_listeners = {
        'StatusMediaListener': ['volume_level', 'title', 'subtitle',
                                'series_title', 'season', 'episode',
                                'artist', 'album_name', 'track', 'images'
                               ],
        'StatusListener': ['volume_level', 'player_state', 'volume_muted',
                           'status_text', 'icon_url'
                          ]
    }

    for lis in lookup_listeners:
        if listener_aux == lis:
            for atributo in lookup_listeners[lis]:
                if hasattr(status, atributo) and lookup_atributos[atributo]:
                    atrib = lookup_atributos[atributo]
                    ESTADOS[cast][lookup_claves[atributo]] = atrib

    lookup_reemplazos = {
        'imagen': 'icono',
        'titulo': 'texto',
        'artista': 'subtitulo'
    }
    # Si al terminar el loop, no tengo algunos datos, los completo con otros
    for cast in ESTADOS:
        for original in lookup_reemplazos:
            reemplazo = lookup_reemplazos[original]
            if reemplazo in ESTADOS[cast]:
                if original not in ESTADOS[cast]:
                    ESTADOS[cast][original] = ESTADOS[cast][reemplazo]
                elif ESTADOS[cast][original] != ESTADOS[cast][reemplazo]:
                    del ESTADOS[cast][reemplazo]

    ahora = datetime.datetime.now()
    ESTADOS[cast]['timestamp'] = ahora.strftime("%Y-%m-%d %H:%M:%S")

    # Si al terminar el loop, no tengo algunos datos, borro el registro
    borrar = []
    for cast in ESTADOS:
        if ('texto' not in ESTADOS[cast] and
                (('estado' in ESTADOS[cast] and
                  ESTADOS[cast]['estado'] == "UNKNOWN"
                 ) or
                 'estado' not in ESTADOS[cast]
                )
           ):
            borrar.append(cast)
    for i in borrar:
        del ESTADOS[i]

class StatusListener:
    """Clase listener para cambios de estado
    """
    def __init__(self, name, cast):
        self.name = name
        self.cast = cast

    def new_cast_status(self, status):
        """Metodo para enviar nuevos estados

        Args:
            status (Response): Estado que se envia al diccionario de estados
        """
        update_status(self, status)


class StatusMediaListener:
    """Clase listener para cambios de contenido multimedia
    """
    def __init__(self, name, cast):
        self.name = name
        self.cast = cast

    def new_media_status(self, status):
        """Metodo para enviar nuevos estados

        Args:
            status (Response): Estado que se envia al diccionario de estados
        """
        update_status(self, status)


def create_listeners():
    """Creacion de listeners y attach a cada objeto Chromecast
    """
    listener = pychromecast.CastListener()
    zconf = zeroconf.Zeroconf()
    browser = pychromecast.discovery.start_discovery(listener, zconf)
    time.sleep(1)
    for uuid, service in listener.services.items():
        cast = pychromecast.get_chromecast_from_service(service, zconf)
        if service[2] == "Chromecast":
            if service[3] not in CHROMECASTS:
                cast.wait()
                listener_cast = StatusListener(cast.name, cast)
                cast.register_status_listener(listener_cast)
                listener_media = StatusMediaListener(cast.name, cast)
                cast.media_controller.register_status_listener(listener_media)
                UUIDS.append(uuid)
                CHROMECASTS[service[3]] = cast

    pychromecast.stop_discovery(browser)

def atender(wsock):
    """Funcion para atender los mensajes del WebSocket

    Args:
        wsock (WebSocket): objeto donde se recibiran los mensajes

    Raises:
        exc: Si ocurre una excepcion de WebSocket se envia al programa principal
    """
    logger=logging.getLogger()
    try:
        message = wsock.receive()
        if message == "init":
            logger.info("%s recibido. Enviando listado de dispositivos.",
                         message)
            wsock.send(str(init()))
        elif message == "update":
            logger.info("%s recibido. Enviando listado de dispositivos.",
                         message)
            wsock.send(str(get_status()))
        elif message:
            comando=message.split(',')
            if comando[0] == "play":
                f_play(cast=comando[1])
            elif comando[0] == "pause":
                f_pause(cast=comando[1])
            elif comando[0] == "back":
                f_back(cast=comando[1])
            elif comando[0] == "forward":
                f_forward(cast=comando[1])
            elif comando[0] == "volume":
                f_volume(cast=comando[1],value=comando[2])
            else:
                print(message)
    except WebSocketError as exc:
        raise exc

def f_back(cast):
    try:
        CHROMECASTS[cast].media_controller.queue_prev()
    except AttributeError:
        pass        

def f_play(cast):
    try:
        CHROMECASTS[cast].media_controller.play()
    except AttributeError:
        pass        

def f_pause(cast):
    try:
        CHROMECASTS[cast].media_controller.pause()
    except AttributeError:
        pass

def f_forward(cast):
    try:
        CHROMECASTS[cast].media_controller.queue_next()
    except AttributeError:
        pass

def f_volume(cast,value):
    CHROMECASTS[cast].set_volume(float(value)/100)
