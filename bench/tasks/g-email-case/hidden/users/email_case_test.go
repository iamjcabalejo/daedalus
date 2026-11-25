package users

// Benchmark hidden tests (overlaid at scoring time; not part of the upstream repository).
// They drive the public HTTP API, use their own helper names, and rely on unit_test.go's TestMain
// for the SQLite test database. Unique names keep them independent of other rows.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gothinkster/golang-gin-realworld-example-app/common"
	"golang.org/x/crypto/bcrypt"
)

const hiddenACEmailPassword = "password123"

func hiddenACEmailRouter() *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.RedirectTrailingSlash = false
	v1 := r.Group("/api")
	UsersRegister(v1.Group("/users"))
	v1.Use(AuthMiddleware(true))
	UserRegister(v1.Group("/user"))
	return r
}

func hiddenACEmailCall(t *testing.T, r *gin.Engine, method, path, token string, body interface{}) (int, map[string]interface{}) {
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

func hiddenACEmailUser(out map[string]interface{}) map[string]interface{} {
	user, _ := out["user"].(map[string]interface{})
	if user == nil {
		return map[string]interface{}{}
	}
	return user
}

func hiddenACEmailRegister(t *testing.T, r *gin.Engine, username, email string) (int, map[string]interface{}) {
	t.Helper()
	return hiddenACEmailCall(t, r, "POST", "/api/users", "", map[string]interface{}{
		"user": map[string]string{"username": username, "email": email, "password": hiddenACEmailPassword},
	})
}

func hiddenACEmailLogin(t *testing.T, r *gin.Engine, email, password string) (int, map[string]interface{}) {
	t.Helper()
	return hiddenACEmailCall(t, r, "POST", "/api/users/login", "", map[string]interface{}{
		"user": map[string]string{"email": email, "password": password},
	})
}

func hiddenACEmailSuffix() string {
	return fmt.Sprintf("%d", time.Now().UnixNano()%1000000000)
}

func TestHiddenACEmailRegistrationStoresLowercase(t *testing.T) {
	r := hiddenACEmailRouter()
	sfx := hiddenACEmailSuffix()
	mixed := "Mixed.Case" + sfx + "@Example.COM"

	code, out := hiddenACEmailRegister(t, r, "mixedcase"+sfx, mixed)
	if code != http.StatusCreated {
		t.Fatalf("register with %s: status %d, body %v", mixed, code, out)
	}
	if got, want := hiddenACEmailUser(out)["email"], strings.ToLower(mixed); got != want {
		t.Errorf("registration response email: got %v, want %v", got, want)
	}
	stored, err := FindOneUser(&UserModel{Username: "mixedcase" + sfx})
	if err != nil {
		t.Fatalf("load registered user: %v", err)
	}
	if stored.Email != strings.ToLower(mixed) {
		t.Errorf("stored email: got %q, want %q", stored.Email, strings.ToLower(mixed))
	}
}

func TestHiddenACEmailLoginIgnoresCase(t *testing.T) {
	r := hiddenACEmailRouter()
	sfx := hiddenACEmailSuffix()
	email := "Login.Case" + sfx + "@Example.com"
	if code, out := hiddenACEmailRegister(t, r, "logincase"+sfx, email); code != http.StatusCreated {
		t.Fatalf("register: status %d, body %v", code, out)
	}

	for _, variant := range []string{strings.ToUpper(email), strings.ToLower(email), email} {
		code, out := hiddenACEmailLogin(t, r, variant, hiddenACEmailPassword)
		if code != http.StatusOK {
			t.Errorf("login as %s: status %d, want 200 (body %v)", variant, code, out)
			continue
		}
		if token, _ := hiddenACEmailUser(out)["token"].(string); token == "" {
			t.Errorf("login as %s: no token in %v", variant, out)
		}
	}
	if code, _ := hiddenACEmailLogin(t, r, strings.ToUpper(email), "wrong-password-1"); code != http.StatusUnauthorized {
		t.Errorf("login with a wrong password: status %d, want 401", code)
	}
}

func TestHiddenACEmailDuplicateIgnoresCase(t *testing.T) {
	r := hiddenACEmailRouter()
	sfx := hiddenACEmailSuffix()
	email := "dup" + sfx + "@example.com"
	if code, out := hiddenACEmailRegister(t, r, "dupfirst"+sfx, email); code != http.StatusCreated {
		t.Fatalf("register first account: status %d, body %v", code, out)
	}

	code, out := hiddenACEmailRegister(t, r, "dupsecond"+sfx, "DUP"+sfx+"@Example.COM")
	if code != http.StatusConflict {
		t.Fatalf("register a case variant of a taken email: status %d, want 409 (body %v)", code, out)
	}
	errs, _ := out["errors"].(map[string]interface{})
	if _, ok := errs["email"]; !ok {
		t.Errorf("409 body should name the email field: %v", out)
	}
	if _, err := FindOneUser(&UserModel{Username: "dupsecond" + sfx}); err == nil {
		t.Errorf("the second account must not be created")
	}
}

func TestHiddenACEmailLegacyMixedCaseAccount(t *testing.T) {
	r := hiddenACEmailRouter()
	sfx := hiddenACEmailSuffix()
	legacyEmail := "Legacy.User" + sfx + "@Example.com"
	hash, err := bcrypt.GenerateFromPassword([]byte(hiddenACEmailPassword), bcrypt.DefaultCost)
	if err != nil {
		t.Fatalf("hash password: %v", err)
	}
	legacy := UserModel{Username: "legacyuser" + sfx, Email: legacyEmail, PasswordHash: string(hash)}
	if err := common.GetDB().Create(&legacy).Error; err != nil {
		t.Fatalf("insert legacy account: %v", err)
	}

	if code, out := hiddenACEmailLogin(t, r, strings.ToLower(legacyEmail), hiddenACEmailPassword); code != http.StatusOK {
		t.Errorf("login to a legacy mixed-case account with the lowercase email: status %d, want 200 (body %v)", code, out)
	}
	if code, out := hiddenACEmailRegister(t, r, "legacyclone"+sfx, strings.ToUpper(legacyEmail)); code != http.StatusConflict {
		t.Errorf("register a case variant of a legacy email: status %d, want 409 (body %v)", code, out)
	}
}

func TestHiddenACEmailUpdate(t *testing.T) {
	r := hiddenACEmailRouter()
	sfx := hiddenACEmailSuffix()
	code, out := hiddenACEmailRegister(t, r, "updater"+sfx, "updater"+sfx+"@example.com")
	if code != http.StatusCreated {
		t.Fatalf("register updater: status %d, body %v", code, out)
	}
	token, _ := hiddenACEmailUser(out)["token"].(string)
	if code, out := hiddenACEmailRegister(t, r, "occupant"+sfx, "occupant"+sfx+"@example.com"); code != http.StatusCreated {
		t.Fatalf("register occupant: status %d, body %v", code, out)
	}

	newEmail := "New.Address" + sfx + "@Example.ORG"
	code, out = hiddenACEmailCall(t, r, "PUT", "/api/user", token, map[string]interface{}{
		"user": map[string]string{"email": newEmail},
	})
	if code != http.StatusOK {
		t.Fatalf("update email: status %d, body %v", code, out)
	}
	if got, want := hiddenACEmailUser(out)["email"], strings.ToLower(newEmail); got != want {
		t.Errorf("updated email in response: got %v, want %v", got, want)
	}
	if code, out := hiddenACEmailLogin(t, r, strings.ToLower(newEmail), hiddenACEmailPassword); code != http.StatusOK {
		t.Errorf("login with the updated email: status %d, want 200 (body %v)", code, out)
	}

	code, out = hiddenACEmailCall(t, r, "PUT", "/api/user", token, map[string]interface{}{
		"user": map[string]string{"email": "OCCUPANT" + sfx + "@EXAMPLE.COM"},
	})
	if code != http.StatusConflict {
		t.Errorf("update to a case variant of another account's email: status %d, want 409 (body %v)", code, out)
	}
	me, err := FindOneUser(&UserModel{Username: "updater" + sfx})
	if err != nil {
		t.Fatalf("load updater: %v", err)
	}
	if me.Email != strings.ToLower(newEmail) {
		t.Errorf("after the rejected update the email should still be %q, got %q", strings.ToLower(newEmail), me.Email)
	}
}
