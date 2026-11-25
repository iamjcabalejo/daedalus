"""Benchmark hidden tests (overlaid at scoring time; not part of the upstream repository).

They call the public API with DRF's test client and check the database afterwards, so they don't depend
on how the permission check is implemented (view code, a permission class, or a queryset filter).
"""
from django.test import TestCase
from rest_framework.test import APIClient

from conduit.apps.articles.models import Article, Comment
from conduit.apps.authentication.models import User

REJECTED_ANONYMOUS = (401, 403)


class ArticleAndCommentOwnershipTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            'article_author', 'article_author@example.com', 'correct-horse-1'
        )
        self.commenter = User.objects.create_user(
            'commenter', 'commenter@example.com', 'correct-horse-2'
        )
        self.stranger = User.objects.create_user(
            'stranger', 'stranger@example.com', 'correct-horse-3'
        )
        self.article = Article.objects.create(
            author=self.author.profile,
            slug='original-title-a1b2c3',
            title='Original title',
            description='Original description',
            body='Original body',
        )
        self.other_article = Article.objects.create(
            author=self.author.profile,
            slug='another-article-d4e5f6',
            title='Another article',
            description='Another description',
            body='Another body',
        )
        self.comment = Comment.objects.create(
            article=self.article,
            author=self.commenter.profile,
            body='A reader comment',
        )

    def client_for(self, user):
        client = APIClient()
        if user is not None:
            client.credentials(HTTP_AUTHORIZATION='Token ' + user.token)
        return client

    def article_url(self, slug=None):
        return '/api/articles/' + (slug or self.article.slug)

    def comment_url(self, slug=None, pk=None):
        return '/api/articles/{}/comments/{}'.format(
            slug or self.article.slug, pk or self.comment.pk
        )

    def assert_article_unchanged(self):
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, 'Original title')
        self.assertEqual(self.article.description, 'Original description')
        self.assertEqual(self.article.body, 'Original body')

    def assert_comment_kept(self):
        self.assertTrue(Comment.objects.filter(pk=self.comment.pk).exists())

    # Articles

    def test_other_user_cannot_update_article(self):
        response = self.client_for(self.stranger).put(
            self.article_url(),
            {'article': {'title': 'Hijacked title', 'body': 'Hijacked body'}},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assert_article_unchanged()

    def test_commenter_cannot_update_article(self):
        response = self.client_for(self.commenter).put(
            self.article_url(),
            {'article': {'description': 'Rewritten by a reader'}},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assert_article_unchanged()

    def test_author_can_update_article(self):
        response = self.client_for(self.author).put(
            self.article_url(),
            {'article': {'title': 'Better title', 'body': 'Better body'}},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, 'Better title')
        self.assertEqual(self.article.body, 'Better body')

    def test_anonymous_cannot_update_article(self):
        response = self.client_for(None).put(
            self.article_url(), {'article': {'title': 'Anonymous'}}, format='json'
        )
        self.assertIn(response.status_code, REJECTED_ANONYMOUS)
        self.assert_article_unchanged()

    # Comments

    def test_stranger_cannot_delete_comment(self):
        response = self.client_for(self.stranger).delete(self.comment_url())
        self.assertEqual(response.status_code, 403)
        self.assert_comment_kept()

    def test_article_author_cannot_delete_someone_elses_comment(self):
        response = self.client_for(self.author).delete(self.comment_url())
        self.assertEqual(response.status_code, 403)
        self.assert_comment_kept()

    def test_comment_on_another_article_is_not_found(self):
        response = self.client_for(self.commenter).delete(
            self.comment_url(slug=self.other_article.slug)
        )
        self.assertEqual(response.status_code, 404)
        self.assert_comment_kept()

    def test_unknown_comment_is_not_found(self):
        response = self.client_for(self.commenter).delete(self.comment_url(pk=987654))
        self.assertEqual(response.status_code, 404)
        self.assert_comment_kept()

    def test_comment_author_can_delete_comment(self):
        response = self.client_for(self.commenter).delete(self.comment_url())
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Comment.objects.filter(pk=self.comment.pk).exists())

    def test_anonymous_cannot_delete_comment(self):
        response = self.client_for(None).delete(self.comment_url())
        self.assertIn(response.status_code, REJECTED_ANONYMOUS)
        self.assert_comment_kept()
