-- query.sql — SQL fixture for CodeMirror syntax highlighting test.
-- Exercises: CREATE TABLE, constraints, INSERT, SELECT with JOIN,
-- subquery, aggregate, GROUP BY, HAVING, window function.

-- Schema: a simple blog application

CREATE TABLE users (
    id         SERIAL PRIMARY KEY,
    username   VARCHAR(64)  NOT NULL UNIQUE,
    email      VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE TABLE posts (
    id           SERIAL PRIMARY KEY,
    author_id    INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title        VARCHAR(255) NOT NULL,
    slug         VARCHAR(255) NOT NULL UNIQUE,
    body         TEXT         NOT NULL,
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE tags (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE
);

CREATE TABLE post_tags (
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
    PRIMARY KEY (post_id, tag_id)
);

CREATE INDEX idx_posts_author   ON posts(author_id);
CREATE INDEX idx_posts_pub_date ON posts(published_at DESC NULLS LAST);

-- Sample data
INSERT INTO users (username, email) VALUES
    ('alice', 'alice@example.com'),
    ('bob',   'bob@example.com'),
    ('carol', 'carol@example.com');

INSERT INTO tags (name) VALUES ('tech'), ('devops'), ('rust'), ('python');

-- Published posts with tag join
SELECT
    p.id,
    p.title,
    u.username            AS author,
    p.published_at,
    COUNT(pt.tag_id)      AS tag_count,
    STRING_AGG(t.name, ', ' ORDER BY t.name) AS tags
FROM posts          p
JOIN users          u  ON u.id = p.author_id
LEFT JOIN post_tags pt ON pt.post_id = p.id
LEFT JOIN tags      t  ON t.id = pt.tag_id
WHERE p.published_at IS NOT NULL
  AND p.published_at <= NOW()
GROUP BY p.id, p.title, u.username, p.published_at
HAVING COUNT(pt.tag_id) > 0
ORDER BY p.published_at DESC
LIMIT 20;

-- Authors ranked by post count using a window function
SELECT
    u.username,
    COUNT(p.id)                                     AS post_count,
    RANK() OVER (ORDER BY COUNT(p.id) DESC)         AS rank,
    ROUND(
        COUNT(p.id) * 100.0 / SUM(COUNT(p.id)) OVER (),
        1
    )                                               AS pct_of_total
FROM users u
LEFT JOIN posts p ON p.author_id = u.id AND p.published_at IS NOT NULL
GROUP BY u.id, u.username
ORDER BY rank;
