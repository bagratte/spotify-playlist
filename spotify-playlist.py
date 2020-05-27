#!/usr/bin/env python3

import argparse
import collections
import itertools
import os
import typing

import spotipy
import spotipy.util
import yaml


class Config(collections.UserDict):
    def __init__(self, path: str):
        self.path = path
        try:
            with open(path) as f:
                self.data = yaml.safe_load(f)
                if self.data is None:
                    self.data = {}
        except FileNotFoundError:
            self.data = {}

    def save(self):
        with open(self.path, 'w') as f:
            yaml.dump(self.data, f)


class Playlist:
    '''Spotify playlist.

    Methods:

    Attributes:
    '''

    def __init__(self, name: str) -> None:

        '''Initialize the playlist.

        Arguments:
            name: The name of the Spotify playlist.
        '''

        config_dir = f'{os.path.expanduser("~")}/.spotify-playlist'
        os.makedirs(config_dir, exist_ok=True)

        self.config = Config(os.path.join(config_dir, 'config.yml'))
        if not self.config.get('username', False):
            self.config['username'] = input('Type your Spotify username: ')
            self.config.save()

        cache_path = os.path.join(config_dir, self.config['username'])
        token = spotipy.util.prompt_for_user_token(
            username=self.config['username'],
            scope=','.join(
                [
                    'playlist-read-private',
                    'playlist-modify-private',
                    'user-follow-read',
                    'user-follow-modify'
                ]
            ),
            client_id='7f905930cf3848e2b53b59e5cf9bca72',
            client_secret='82b0b7e333d344959247b733287e82d7',
            redirect_uri='http://localhost:8080/',
            cache_path=cache_path
        )
        self.spotify = spotipy.Spotify(auth=token)

        self.name = name


    @property
    def playlist(self):

        '''Writable playlist.'''

        try:
            r = [
                p for p in self.paginate_all(
                    self.spotify.current_user_playlists
                )
                if p['name'] == self.name
            ][0]
        except IndexError:
            r = self.spotify.user_playlist_create(
                self.config['username'],
                self.name,
                public=False
            )
        return r

    @property
    def parts(self):

        '''Rolled over playlists.'''

        return [
            p for p in self.paginate_all(self.spotify.current_user_playlists)
            if p['name'].startswith(f'{self.name}-')
        ]

    def add_artist(self, artist_id: str) -> None:

        '''Add artist to playlist.

        Arguments:
            artist_id: Spotify URL, URI or ID of the artist to add.
        '''

        artist = self.spotify.artist(artist_id)

        if artist['id'] in self.config.get(
            'playlists', {}
        ).get(
            self.playlist['name'], []
        ):
            print(f'{artist["name"]} already in {self.playlist["name"]}.')
            return

        print(f'Adding {artist["name"]} to {self.playlist["name"]}...')
        albums = self.paginate_all(
            self.spotify.artist_albums,
            artist['id'],
            album_type='album,single,compilation'
        )
        self.add_albums(albums)
        self.config.setdefault(
            'playlists', {}
        ).setdefault(
            self.playlist['name'], []
        ).append(artist['id'])
        self.config.save()

    def remove_artist(self, artist_id: str) -> None:

        '''Remove artist from playlist.

        Arguments:
            artist_id: Spotify URL, URI or ID of the artist to remove.
        '''

        artist = self.spotify.artist(artist_id)

        if artist['id'] not in self.config.get(
            'playlists', {}
        ).get(
            self.playlist['name'], []
        ):
            print(f'{artist["name"]} not in {self.playlist["name"]}')
            return

        print(f'Removing {artist["name"]} from {self.playlist["name"]}...')
        albums = self.paginate_all(
            self.spotify.artist_albums,
            artist['id'],
            album_type='album,single,compilation'
        )
        self.remove_albums(albums)
        self.config['playlists'][self.playlist['name']].remove(artist['id'])
        self.config.save()

    def update(self) -> None:

        '''Add new albums from artists in playlist.'''

        album_ids_0 = {
            t['track']['album']['id']
            for p in self.parts + [self.playlist]
            for t in self.paginate_all(
                self.spotify._get,
                f'playlists/{p["id"]}/tracks'
            )
        }
        for artist_id in self.config['playlists'][self.playlist['name']]:
            album_ids_1 = {
                a['id']
                for a in self.paginate_all(
                    self.spotify.artist_albums,
                    artist_id,
                    album_type='album,single,compilation'
                )
            }
            diff = [
                self.spotify.album(a_id)
                for a_id in album_ids_1 - album_ids_0
            ]
            for album in diff:
                self.add_album(album)
                artists = [a['name'] for a in album['artists']]
                print(f'{album["name"]} - {", ".join(artists)}')

    def add_albums(self, albums: typing.List[typing.Mapping]) -> None:

        '''Add albums to playlist.

        Arguments:
            albums: List of Spotify albums to add.
        '''

        for album in albums:
            self.add_album(album)

    def remove_albums(self, albums: typing.List[typing.Mapping]) -> None:

        '''Remove albums from playlist.

        Arguments:
            albums: List of Spotify albums to remove.
        '''

        for album in albums:
            self.remove_album(album)

    def add_album(self, album: typing.Mapping):

        '''Add album to playlist.

        Arguments:
            album: Spotify album to add.
        '''

        tracks = self.paginate_all(self.spotify.album_tracks, album['id'])
        if self.playlist['tracks']['total'] + len(tracks) >= 10000:
            self.rollover()
        for batch in itertools.zip_longest(*([iter(tracks)] * 100)):
            self.spotify.user_playlist_add_tracks(
                self.config['username'],
                self.playlist['id'],
                (t['id'] for t in filter(None, batch))
            )

    def remove_album(self, album: typing.Mapping):

        '''Remove album to playlist.

        Arguments:
            album: Spotify album to remove.
        '''

        tracks = self.paginate_all(self.spotify.album_tracks, album['id'])
        for p in self.parts + [self.playlist]:
            for batch in itertools.zip_longest(*([iter(tracks)] * 100)):
                self.spotify.user_playlist_remove_all_occurrences_of_tracks(
                    self.config['username'],
                    self.playlist['id'],
                    (t['id'] for t in filter(None, batch))
                )

    def rollover(self) -> None:

        '''Rollover playlist.'''

        if self.parts:
            i = max(int(p['name'].split('-')[-1]) for p in self.parts) + 1
        else:
            i = 1
        self.spotify.user_playlist_change_details(
            self.config['username'],
            self.playlist['id'],
            name=f'{self.name}-{i}'
        )
        self.spotify.user_playlist_create(
            self.config['username'],
            self.name,
            public=False
        )

    def paginate_all(self,
            method: typing.Callable[..., typing.Mapping],
            *args,
            **kwargs) -> typing.List:

        '''Paginate and return all results of method.

        Arguments:
            method: spotipy.Spotify method
        '''

        page = method(*args, **kwargs)
        result = page['items']
        while page['next']:
            page = self.spotify.next(page)
            result.extend(page['items'])
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        usage='%(prog)s [options] [playlist]',
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    globals_ = parser.add_argument_group('options')
    globals_.add_argument("-c", "--trace", action="store_true", default=False)
    playlist = parser.add_argument_group('playlist')
    playlist.add_argument("playlist")
    playlist.add_argument("-a", "--add", metavar="ARTIST_URI")
    playlist.add_argument("-r", "--remove", metavar="ARTIST_URI")
    playlist.add_argument("-u", "--update", action="store_true", default=False)
    args = parser.parse_args()

    playlist = Playlist(args.playlist)
    playlist.spotify.trace = args.trace
    if args.add:
        playlist.add_artist(args.add)
    if args.remove:
        playlist.remove_artist(args.remove)
    if args.update:
        playlist.update()
