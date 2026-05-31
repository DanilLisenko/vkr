// movies/static/js/load_more.js
$(document).ready(function() {
    let page = 2;
    let loading = false;

    function loadMoreActors() {
        if (loading) return;
        loading = true;

        $.ajax({
            url: '/movies/actors/load-more/',
            type: 'GET',
            data: { page: page },
            success: function(data) {
                let actors = data.actors;
                let hasNext = data.has_next;

                actors.forEach(function(actor) {
                    let actorHtml = `
                        <div class="col-md-4 actor-item" data-aos="fade-up">
                            <a href="${actor.detail_url}" class="text-decoration-none">
                                <div class="card h-100 mb-4">
                                    <img src="${actor.photo_url}" class="card-img-top" alt="${actor.name}">
                                    <div class="card-body">
                                        <h5 class="card-title">${actor.name}</h5>
                                        <p class="card-text">${actor.birth_date}</p>
                                    </div>
                                </div>
                            </a>
                        </div>
                    `;
                    $('.actors-list').append(actorHtml);
                });

                if (hasNext) {
                    page++;
                } else {
                    $('#load-more-btn').hide();
                }
                loading = false;
            },
            error: function() {
                console.log('Error loading more actors');
                loading = false;
            }
        });
    }

    $('#load-more-btn').on('click', function() {
        loadMoreActors();
    });

    $(window).on('scroll', function() {
        if ($(window).scrollTop() + $(window).height() > $(document).height() - 100) {
            loadMoreActors();
        }
    });
});