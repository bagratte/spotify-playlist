#!/usr/bin/env python

import argparse
import os
import subprocess

import spotipy
import spotipy.util


class AuthenticationException(Exception):
    pass

os.environ["SPOTIPY_CLIENT_ID"] = "7f905930cf3848e2b53b59e5cf9bca72"
os.environ["SPOTIPY_CLIENT_SECRET"] = "82b0b7e333d344959247b733287e82d7"
os.environ["SPOTIPY_REDIRECT_URI"] = "http://localhost/"
scope = "playlist-read-private,playlist-modify-private,user-follow-read,user-follow-modify"
cache_dir = f"{os.path.expanduser('~')}/.spotipy"
os.makedirs(cache_dir, exist_ok=True)
cache_path = os.path.join(cache_dir, "bagratte")
token = spotipy.util.prompt_for_user_token("bagratte",
                                           scope,
                                           cache_path=cache_path)
if token:
    sp = spotipy.Spotify(auth=token)
else:
    raise AuthenticationException("Unable to authenticate.")

def paginate_all(method, *args, root=None, **kwargs):
    page = method(*args, **kwargs)
    if root is not None:
        page = page[root]
    result = page["items"]
    while page["next"]:
        page = sp.next(page)
        if root is not None:
            page = page[root]
        result.extend(page["items"])
    return result

def total_tracks_by_artist(artist_id):
    total = 0
    albums = paginate_all(sp.artist_albums, artist_id,
                          album_type="album,single,compilation")
    for album in albums:
        tracks = sp.album_tracks(album["id"])
        total += int(tracks["total"])
    return total

def unfilled_playlist():
    playlists = paginate_all(sp.current_user_playlists)
    unfilled = [p for p in playlists if p["name"] == "omnis-unfilled"]
    if unfilled:
        return unfilled[0]["id"]
    else:
        r = sp.user_playlist_create("bagratte", "omnis-unfilled", public=False)
        return r["id"]

def albums_playlist(playlist_id, album_ids, action):
    actions = {
        "add": sp.user_playlist_add_tracks,
        "remove": sp.user_playlist_remove_all_occurrences_of_tracks,
    }
    if action not in actions:
        raise ValueError(
            "action must be on of {}".format("/".join(actions.keys()))
        )
    action = actions[action]

    total = 0
    for album_id in album_ids:
        r = sp.album_tracks(album_id)
        total += r["total"]
        track_ids = [t["id"] for t in r["items"]]
        action("bagratte", playlist_id, track_ids)
        while r["next"]:
            r = sp.next(r)
            track_ids = [t["id"] for t in r["items"]]
            action("bagratte", playlist_id, track_ids)
    return total

def artists_playlist(playlist_id, artist_ids, action):
    actions = {
        "add": {
            "message": "Adding {} to {}...",
            "diff": lambda before, after: after - before,
            "diffverb": "Added"
        },
        "remove": {
            "message": "Removing {} from {}...",
            "diff": lambda before, after: before - after,
            "diffverb": "Removed"
        }
    }
    if action not in actions:
        raise ValueError(
            "action must be on of {}".format("/".join(actions.keys()))
        )

    for artist_id in artist_ids:
        artist_name = sp.artist(artist_id)["name"]
        playlist = sp.user_playlist("bagratte", playlist_id)
        playlist_name = playlist["name"]
        print(actions[action]["message"].format(artist_name, playlist_name))
        sp.user_follow_artists([artist_id])
        albums = paginate_all(sp.artist_albums, artist_id,
                              album_type="album,single,compilation")

        before = int(playlist["tracks"]["total"])
        added = albums_playlist(playlist_id, (a["id"] for a in albums), action)
        playlist = sp.user_playlist("bagratte", playlist_id)
        after = int(playlist["tracks"]["total"])
        diff = actions[action]["diff"](before, after)
        if diff != added:
            print("WARNING:", end=" ")
        print(f'{actions[action]["diffverb"]} {diff} of {added} tracks to {playlist_name}.')
        print(f"{playlist_name} contains {after} tracks.")

def sync():
    omnis = [
        p for p in paginate_all(sp.current_user_playlists)
        if p["name"].startswith("omnis-")
    ]
    album_ids_1 = {
        a["track"]["album"]["id"]
        for p in omnis
        for a in paginate_all(sp._get,
                              f'playlists/{p["id"]}/tracks',
                              fields="next,items(track.album.id)")
    }
    artists = paginate_all(sp.current_user_followed_artists, root="artists")
    for artist_id in (a["id"] for a in artists):
        album_ids_0 = {
            a["id"]
            for a in paginate_all(sp.artist_albums,
                                artist_id,
                                album_type="album,single,compilation")
        }
        diff = album_ids_0 - album_ids_1
        albums_playlist(unfilled_playlist(), diff, "add")
        for album_id in diff:
            album = sp.album(album_id)
            artists = [a["name"] for a in album["artists"]]
            message = f'Added {album["name"]} by {", ".join(artists)}'
            notify(message)

def notify(message):
    try:
        subprocess.run(["notify-send", "Spotify Sync", message])
    except Exception:
        print(message)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-a", "--add", metavar="ARTIST_URI")
    parser.add_argument("-r", "--remove", metavar="ARTIST_URI")
    parser.add_argument("-t", "--total", metavar="ARTIST_URI")
    parser.add_argument("-s", "--sync", action="store_true", default=False)
    parser.add_argument("-c", "--trace", action="store_true", default=False)
    args = parser.parse_args()

    sp.trace = args.trace
    if args.add:
        unfilled_id = unfilled_playlist()
        artists_playlist(unfilled_id, [args.add], "add")
    if args.remove:
        unfilled_id = unfilled_playlist()
        artists_playlist(unfilled_id, [args.remove], "remove")
    if args.total:
        print(total_tracks_by_artist(args.total))
    if args.sync:
        sync()
