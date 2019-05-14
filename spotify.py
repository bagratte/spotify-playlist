#!/usr/bin/env python

import argparse
import os

import spotipy
import spotipy.util


class AuthenticationException(Exception):
    pass

os.environ["SPOTIPY_CLIENT_ID"] = "7f905930cf3848e2b53b59e5cf9bca72"
os.environ["SPOTIPY_CLIENT_SECRET"] = "82b0b7e333d344959247b733287e82d7"
os.environ["SPOTIPY_REDIRECT_URI"] = "http://localhost/"
scope = "playlist-read-private,playlist-modify-private,user-follow-modify"
token = spotipy.util.prompt_for_user_token("bagratte", scope)
if token:
    sp = spotipy.Spotify(auth=token)
else:
    raise AuthenticationException("Unable to authenticate.")

def paginate_all(method, *args, **kwargs):
    page = method(*args, **kwargs)
    result = page["items"]
    while page["next"]:
        page = sp.next(page)
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
    unfilled = [p for p in playlists if p["name"] == "unfilled"]
    if unfilled:
        return unfilled[0]["id"]
    else:
        r = sp.user_playlist_create("bagratte", "unfilled", public=False)
        return r["id"]

def artists_playlist(playlist_id, artist_ids, action):
    actions = {
        "add": {
            "action": sp.user_playlist_add_tracks,
            "message": "Adding {} to {}...",
            "diff": lambda before, after: after - before,
            "diffverb": "Added"
        },
        "remove": {
            "action": sp.user_playlist_remove_all_occurrences_of_tracks,
            "message": "Removing {} from {}...",
            "diff": lambda before, after: before - after,
            "diffverb": "Removed"
        }
    }
    if action not in actions:
        raise ValueError(
            "action must be on of {}".format("/".join(actions.keys()))
        )
    action = actions[action]

    for artist_id in artist_ids:
        artist_name = sp.artist(artist_id)["name"]
        playlist = sp.user_playlist("bagratte", playlist_id)
        playlist_name = playlist["name"]
        print(action["message"].format(artist_name, playlist_name))
        sp.user_follow_artists([artist_id])
        albums = paginate_all(sp.artist_albums, artist_id,
                              album_type="album,single,compilation")

        before = int(playlist["tracks"]["total"])
        total = 0
        for album in albums:
            r = sp.album_tracks(album["id"])
            total += r["total"]
            track_ids = [t["id"] for t in r["items"]]
            action["action"]("bagratte", playlist_id, track_ids)
            while r["next"]:
                r = sp.next(r)
                track_ids = [t["id"] for t in r["items"]]
                action["action"]("bagratte", playlist_id, track_ids)

        playlist = sp.user_playlist("bagratte", playlist_id)
        after = int(playlist["tracks"]["total"])
        diff = action["diff"](before, after)
        if diff != total:
            print("WARNING:", end=" ")
        print(f'{action["diffverb"]} {diff} of {total} tracks to {playlist_name}.')
        print(f"{playlist_name} contains {after} tracks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-a", "--add", metavar="ARTIST_URI")
    parser.add_argument("-r", "--remove", metavar="ARTIST_URI")
    parser.add_argument("-t", "--total", metavar="ARTIST_URI")
    parser.add_argument("-c", "--trace", action="store_true", default=False)
    args = parser.parse_args()

    sp.trace = args.trace
    if args.add:
        unfilled_id = unfilled_playlist()
        artists_playlist(unfilled_id, [args.add], "add")
    if args.remove:
        unfilled_id = unfilled_playlist()
        artists_playlist(unfilled_id, [args.add], "remove")
    if args.total:
        print(total_tracks_by_artist(args.total))
