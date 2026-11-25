package articles

// Benchmark hidden tests (overlaid at scoring time; not part of the upstream repository).
// They drive the public HTTP API only and use their own helper names, so they don't depend on
// helpers in unit_test.go beyond its TestMain (which opens and migrates the test database).

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sort"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gothinkster/golang-gin-realworld-example-app/users"
)

func hiddenACFiltersRouter() *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.RedirectTrailingSlash = false
	v1 := r.Group("/api")
	users.UsersRegister(v1.Group("/users"))
	v1.Use(users.AuthMiddleware(false))
	ArticlesAnonymousRegister(v1.Group("/articles"))
	v1.Use(users.AuthMiddleware(true))
	ArticlesRegister(v1.Group("/articles"))
	return r
}

func hiddenACFiltersCall(t *testing.T, r *gin.Engine, method, path, token string, body interface{}) (int, map[string]interface{}) {
	t.Helper()
	var payload []byte
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("encode request body: %v", err)
		}
		payload = encoded
	}
	req, err := http.NewRequest(method, path, bytes.NewReader(payload))
	if err != nil {
		t.Fatalf("build request %s %s: %v", method, path, err)
	}
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Token "+token)
	}
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	out := map[string]interface{}{}
	_ = json.Unmarshal(w.Body.Bytes(), &out)
	return w.Code, out
}

func hiddenACFiltersRegister(t *testing.T, r *gin.Engine, username string) string {
	t.Helper()
	code, out := hiddenACFiltersCall(t, r, "POST", "/api/users", "", map[string]interface{}{
		"user": map[string]string{"username": username, "email": username + "@example.com", "password": "password123"},
	})
	if code != http.StatusCreated {
		t.Fatalf("register %s: status %d, body %v", username, code, out)
	}
	user, _ := out["user"].(map[string]interface{})
	token, _ := user["token"].(string)
	if token == "" {
		t.Fatalf("register %s: no token in %v", username, out)
	}
	return token
}

func hiddenACFiltersPublish(t *testing.T, r *gin.Engine, token, title string, tags []string) string {
	t.Helper()
	code, out := hiddenACFiltersCall(t, r, "POST", "/api/articles", token, map[string]interface{}{
		"article": map[string]interface{}{"title": title, "description": "about " + title, "body": "body of " + title, "tagList": tags},
	})
	if code != http.StatusCreated {
		t.Fatalf("create article %q: status %d, body %v", title, code, out)
	}
	article, _ := out["article"].(map[string]interface{})
	slug, _ := article["slug"].(string)
	if slug == "" {
		t.Fatalf("create article %q: no slug in %v", title, out)
	}
	return slug
}

func hiddenACFiltersFavorite(t *testing.T, r *gin.Engine, token, slug string) {
	t.Helper()
	code, out := hiddenACFiltersCall(t, r, "POST", "/api/articles/"+slug+"/favorite", token, nil)
	if code != http.StatusOK {
		t.Fatalf("favorite %s: status %d, body %v", slug, code, out)
	}
}

func hiddenACFiltersList(t *testing.T, r *gin.Engine, query string) ([]string, int) {
	t.Helper()
	code, out := hiddenACFiltersCall(t, r, "GET", "/api/articles?"+query, "", nil)
	if code != http.StatusOK {
		t.Fatalf("GET /api/articles?%s: status %d, body %v", query, code, out)
	}
	items, _ := out["articles"].([]interface{})
	slugs := []string{}
	for _, item := range items {
		article, _ := item.(map[string]interface{})
		slug, _ := article["slug"].(string)
		slugs = append(slugs, slug)
	}
	sort.Strings(slugs)
	count, ok := out["articlesCount"].(float64)
	if !ok {
		t.Fatalf("GET /api/articles?%s: no numeric articlesCount in %v", query, out)
	}
	return slugs, int(count)
}

func hiddenACFiltersSorted(values ...string) []string {
	out := append([]string{}, values...)
	sort.Strings(out)
	return out
}

func TestHiddenACListFiltersCombine(t *testing.T) {
	r := hiddenACFiltersRouter()
	sfx := fmt.Sprintf("%d", time.Now().UnixNano()%1000000000)
	alice, bob, carol := "alice"+sfx, "bob"+sfx, "carol"+sfx
	aliceToken := hiddenACFiltersRegister(t, r, alice)
	bobToken := hiddenACFiltersRegister(t, r, bob)
	carolToken := hiddenACFiltersRegister(t, r, carol)

	tagX, tagY := "dragons"+sfx, "castles"+sfx
	aliceDragons := hiddenACFiltersPublish(t, r, aliceToken, "Alice on dragons "+sfx, []string{tagX})
	aliceCastles := hiddenACFiltersPublish(t, r, aliceToken, "Alice on castles "+sfx, []string{tagY})
	bobBoth := hiddenACFiltersPublish(t, r, bobToken, "Bob on dragons and castles "+sfx, []string{tagX, tagY})
	hiddenACFiltersFavorite(t, r, carolToken, aliceDragons)
	hiddenACFiltersFavorite(t, r, carolToken, bobBoth)

	cases := []struct {
		name  string
		query string
		want  []string
	}{
		{"tag and author", "tag=" + tagX + "&author=" + alice, []string{aliceDragons}},
		{"tag and other author", "tag=" + tagY + "&author=" + bob, []string{bobBoth}},
		{"author and favorited", "author=" + alice + "&favorited=" + carol, []string{aliceDragons}},
		{"tag and favorited", "tag=" + tagX + "&favorited=" + carol, hiddenACFiltersSorted(aliceDragons, bobBoth)},
		{"all three", "tag=" + tagX + "&author=" + alice + "&favorited=" + carol, []string{aliceDragons}},
		{"all three, no match", "tag=" + tagY + "&author=" + alice + "&favorited=" + carol, []string{}},
		{"unknown tag with author", "tag=nosuchtag" + sfx + "&author=" + alice, []string{}},
		{"tag with unknown author", "tag=" + tagX + "&author=nosuchuser" + sfx, []string{}},
		{"tag with unknown favoriter", "tag=" + tagX + "&favorited=nosuchuser" + sfx, []string{}},
		{"tag alone", "tag=" + tagX, hiddenACFiltersSorted(aliceDragons, bobBoth)},
		{"author alone", "author=" + alice, hiddenACFiltersSorted(aliceDragons, aliceCastles)},
		{"favorited alone", "favorited=" + carol, hiddenACFiltersSorted(aliceDragons, bobBoth)},
	}
	for _, tc := range cases {
		got, count := hiddenACFiltersList(t, r, tc.query)
		want := hiddenACFiltersSorted(tc.want...)
		if fmt.Sprint(got) != fmt.Sprint(want) {
			t.Errorf("%s (%s): got articles %v, want %v", tc.name, tc.query, got, want)
		}
		if count != len(want) {
			t.Errorf("%s (%s): got articlesCount %d, want %d", tc.name, tc.query, count, len(want))
		}
	}
}

func TestHiddenACListFiltersCombineWithPaging(t *testing.T) {
	r := hiddenACFiltersRouter()
	sfx := fmt.Sprintf("%d", time.Now().UnixNano()%1000000000)
	dana, erin := "dana"+sfx, "erin"+sfx
	danaToken := hiddenACFiltersRegister(t, r, dana)
	erinToken := hiddenACFiltersRegister(t, r, erin)
	tag := "paging" + sfx
	first := hiddenACFiltersPublish(t, r, danaToken, "Dana first "+sfx, []string{tag})
	second := hiddenACFiltersPublish(t, r, danaToken, "Dana second "+sfx, []string{tag})
	hiddenACFiltersPublish(t, r, danaToken, "Dana untagged "+sfx, []string{})
	hiddenACFiltersPublish(t, r, erinToken, "Erin tagged "+sfx, []string{tag})

	page, count := hiddenACFiltersList(t, r, "tag="+tag+"&author="+dana+"&limit=1&offset=0")
	if count != 2 {
		t.Errorf("articlesCount for tag+author with limit=1: got %d, want 2 (the count ignores paging)", count)
	}
	if len(page) != 1 {
		t.Fatalf("tag+author with limit=1: got %d articles, want 1", len(page))
	}
	rest, _ := hiddenACFiltersList(t, r, "tag="+tag+"&author="+dana+"&limit=1&offset=1")
	if len(rest) != 1 {
		t.Fatalf("tag+author with limit=1&offset=1: got %d articles, want 1", len(rest))
	}
	got := hiddenACFiltersSorted(page[0], rest[0])
	want := hiddenACFiltersSorted(first, second)
	if fmt.Sprint(got) != fmt.Sprint(want) {
		t.Errorf("two pages of tag+author: got %v, want %v", got, want)
	}
}
