from app.infrastructure.external.tmdbv3api.tmdb import TMDb


class Episode(TMDb):
    _urls = {"images": "/tv/%s/season/%s/episode/%s/images"}

    def images(self, tv_id, season_num, episode_num, include_image_language=None):
        """
        Get the images that belong to a TV episode.
        :param tv_id: int
        :param season_num: int
        :param episode_num: int
        :param include_image_language: str
        :return:
        """
        return self._get_obj(
            self._call(
                self._urls["images"] % (tv_id, season_num, episode_num),
                f"include_image_language={include_image_language}" if include_image_language else "",
            ),
            "stills",
        )
