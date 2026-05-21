const express = require("express");
const { postgraphile } = require("postgraphile");
const ConnectionFilterPlugin = require("postgraphile-plugin-connection-filter");

const app = express();

const ADMIN_SECRET = process.env.ADMIN_SECRET;

app.use("/graphql", (req, res, next) => {
  if (ADMIN_SECRET && req.headers["x-hasura-admin-secret"] !== ADMIN_SECRET) {
    return res.status(401).json({ error: "Unauthorized" });
  }
  next();
});

app.use(
  postgraphile(process.env.DATABASE_URL, "public", {
    appendPlugins: [ConnectionFilterPlugin],
    watchPg: false,
    graphiql: false,
    enhanceGraphiql: false,
    dynamicJson: true,
    setofFunctionsContainNulls: false,
    ignoreRBAC: false,
    showErrorStack: false,
    extendedErrors: [],
    graphqlRoute: "/graphql",
    legacyRelations: "omit",
    simpleCollections: "both",
  })
);

app.get("/healthz", (req, res) => res.send("ok"));

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`PostGraphile on port ${PORT}`));
