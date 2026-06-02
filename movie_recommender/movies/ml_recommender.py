"""
Content-based similarity recommender.
Uses the pre-computed MovieSimilarity matrix (built via build_similarity command)
with Jaccard-based genre similarity and weighted feature combination.
"""
from movies.models import Movie, Review, MovieSimilarity


def get_content_recommendations(user, limit=10):
    """
    Returns up to `limit` recommended movies for `user` based on:
    - MovieSimilarity matrix (genres/actors/crew/tags/rating/year weighted scores)
    - User reviews: rating weight = review.rating - 5.5  (positive above average, negative below)
    - Watchlist items: base weight 1.0
    Falls back to top-rated movies for cold-start users.
    """
    from movies.models import Watchlist

    watched_ids = set(Watchlist.objects.filter(user=user).values_list('movie_id', flat=True))
    reviewed_ids = set(Review.objects.filter(user=user).values_list('movie_id', flat=True))
    all_interacted_ids = watched_ids | reviewed_ids

    movie_weights = {m_id: 1.0 for m_id in watched_ids}
    for review in Review.objects.filter(user=user):
        movie_weights[review.movie_id] = review.rating - 5.5

    if not movie_weights:
        return list(
            Movie.objects.filter(poster_url__isnull=False, rating__gte=7.5)
            .exclude(poster_url='')
            .order_by('-rating')[:limit]
        )

    similarity_records = (
        MovieSimilarity.objects
        .filter(first_movie_id__in=movie_weights.keys())
        .exclude(second_movie_id__in=all_interacted_ids)
        .select_related('second_movie')
    )

    candidate_scores = {}
    for record in similarity_records:
        weight = movie_weights.get(record.first_movie_id, 1.0)
        score = record.score * weight
        entry = candidate_scores.setdefault(record.second_movie_id, {'movie': record.second_movie, 'total': 0.0})
        entry['total'] += score

    ranked = sorted(candidate_scores.values(), key=lambda x: x['total'], reverse=True)
    recommended = [e['movie'] for e in ranked if e['total'] > 0][:limit]

    if len(recommended) < limit:
        extra = limit - len(recommended)
        exclude = all_interacted_ids | {m.id for m in recommended}
        recommended += list(
            Movie.objects.filter(poster_url__isnull=False, rating__gte=7.0)
            .exclude(id__in=exclude)
            .order_by('-rating')[:extra]
        )

    return recommended
